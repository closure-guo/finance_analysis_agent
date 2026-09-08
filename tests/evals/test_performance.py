"""add-latency-cost-regression：性能聚合/基线回归/趋势 测试（fixtures 离线）。"""

import json

from evals.performance.measure import (
    aggregate,
    compare_with_baseline,
    detect_trend,
    estimate_cost,
    extract_trace,
    run_offline,
)


def _trace(name="deep_analysis:茅台", latency=12.5, usage=None, obs_usage=None):
    return {
        "id": f"t-{name}",
        "name": name,
        "timestamp": "2026-09-04T10:00:00Z",
        "latency": latency,
        "observations": [
            {
                "type": "GENERATION",
                "model": "glm-4.5",
                "usage": obs_usage or usage or {"input": 500, "output": 200},
            }
        ],
    }


class TestEstimateCost:
    def test_price_table_lookup(self):
        # glm-4.5 输入 2 元/M、输出 6 元/M
        assert estimate_cost(1_000_000, 500_000, "glm-4.5") == 2.0 + 3.0

    def test_default_fallback(self):
        assert estimate_cost(1_000_000, 0, "unknown-model") == 1.0  # DEFAULT_PRICE 输入 1 元/M


class TestExtract:
    def test_generations_usage_summed(self):
        t = {
            "name": "deep_analysis:x",
            "timestamp": "t",
            "latency": 8.0,
            "observations": [
                {"type": "GENERATION", "model": "glm-4.5", "usage": {"input": 100, "output": 50}},
                {"type": "GENERATION", "model": "glm-4.5", "usage": {"input": 200, "output": 100}},
                {"type": "SPAN", "usage": {"input": 9999}},  # 非 GENERATION 忽略
            ],
        }
        s = extract_trace(t)
        assert s.latency_s == 8.0
        assert s.input_tokens == 300
        assert s.output_tokens == 150
        assert s.cost == round(300 / 1e6 * 2 + 150 / 1e6 * 6, 6)
        assert s.mode == "deep"


class TestAggregate:
    def test_mode_split_and_percentiles(self):
        traces = [
            _trace(name="react_loop", latency=0.5),
            _trace(name="react_loop", latency=0.7),
            _trace(name="react_loop", latency=1.5),
            _trace(name="deep_analysis:x", latency=12.0, obs_usage={"input": 1000, "output": 400}),
        ]
        agg, samples = aggregate(traces)
        assert agg.total == 4
        assert agg.by_mode == {"quick": 3, "deep": 1}
        # [0.5, 0.7, 1.5, 12.0] 中位数 = (0.7+1.5)/2
        assert agg.p50_latency_s == 1.1
        assert agg.avg_cost is not None
        assert samples[3].cost > samples[0].cost

    def test_empty(self):
        agg, samples = aggregate([])
        assert agg.total == 0
        assert agg.p50_latency_s is None
        assert samples == []


class TestCompareBaseline:
    def test_regression_detected(self):
        agg, _ = aggregate([_trace(name="react_loop", latency=1.0)])
        # 基线 0.5 → +100% > 30%
        rows = compare_with_baseline(agg, {"avg_latency_s": 0.5})
        row = next(r for r in rows if r["metric"] == "avg_latency_s")
        assert row["regressed"] is True
        assert row["pct_change"] == 1.0

    def test_within_threshold(self):
        agg, _ = aggregate([_trace(name="react_loop", latency=0.55)])
        rows = compare_with_baseline(agg, {"avg_latency_s": 0.5})
        assert next(r for r in rows if r["metric"] == "avg_latency_s")["regressed"] is False

    def test_missing_baseline_skipped(self):
        agg, _ = aggregate([_trace(name="react_loop", latency=0.5)])
        assert compare_with_baseline(agg, {}) == []


class TestTrend:
    def test_monotonic_degradation_alert(self):
        assert detect_trend([1.0, 1.1, 1.21, 1.35]) is True  # 每轮 ≥5% 递增

    def test_flat_or_improving_no_alert(self):
        assert detect_trend([1.0, 1.0, 1.0]) is False
        assert detect_trend([1.5, 1.2, 1.0]) is False
        assert detect_trend([1.0, 1.1]) is False  # 不足 3 轮


class TestRunOffline:
    def test_end_to_end(self):
        traces = [
            _trace(name="react_loop", latency=0.8),
            _trace(name="deep_analysis:x", latency=9.0),
        ]
        result = run_offline(traces, baseline={"avg_latency_s": 1.0})
        assert result["aggregate"].total == 2
        assert result["compares"], "应有基线对比行"
        assert result["trend_alert"] is False


class TestHistoryArchive:
    """3.2 nightly 时序归档：每次运行追加聚合 → 趋势检测消费序列。"""

    def test_append_and_load_history(self, tmp_path):
        from evals.performance.measure import PerfAggregate, append_history, load_history_series

        path = tmp_path / "perf-history.jsonl"
        agg = PerfAggregate(
            total=10,
            by_mode={"deep": 10},
            p50_latency_s=1.0,
            p90_latency_s=2.0,
            avg_total_tokens=100.0,
            avg_cost=0.5,
            avg_latency_s=1.2,
        )
        append_history(path, agg, model="openai/deepseek-v4-flash-0731")
        append_history(path, agg, model="openai/deepseek-v4-flash-0731")
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        rec = json.loads(lines[0])
        assert rec["model"] == "openai/deepseek-v4-flash-0731"
        assert rec["avg_latency_s"] == 1.2
        assert "as_of" in rec
        series = load_history_series(
            path, metric="avg_latency_s", model="openai/deepseek-v4-flash-0731"
        )
        assert series == [1.2, 1.2]

    def test_load_history_filters_by_model(self, tmp_path):
        """跨模型时延不可比：序列按模型过滤（与基线同原则）。"""
        from evals.performance.measure import PerfAggregate, append_history, load_history_series

        path = tmp_path / "h.jsonl"
        agg = PerfAggregate(total=1, by_mode={}, avg_latency_s=1.0)
        append_history(path, agg, model="model-a")
        append_history(path, agg, model="model-b")
        assert load_history_series(path, model="model-a") == [1.0]
        assert load_history_series(path, model="model-c") == []

    def test_run_offline_history_drives_trend_alert(self, tmp_path):
        """归档历史连续 3 轮每轮 ≥5% 劣化 → trend_alert True。"""
        from evals.performance.measure import PerfAggregate, append_history, run_offline

        path = tmp_path / "h.jsonl"
        for lat in (1.0, 1.1, 1.3):  # +10%、+18% 单调劣化
            agg = PerfAggregate(total=5, by_mode={"deep": 5}, avg_latency_s=lat)
            append_history(path, agg, model="m")
        traces = [_trace(latency=1.6)]
        result = run_offline(traces, history_path=path, model="m")
        assert result["trend_alert"] is True

    def test_run_offline_no_history_no_trend(self, tmp_path):
        from evals.performance.measure import run_offline

        result = run_offline([_trace()], history_path=tmp_path / "missing.jsonl", model="m")
        assert result["trend_alert"] is False

    def test_run_offline_history_model_mismatch_no_trend(self, tmp_path):
        """当前模型无归档序列时不判趋势（跨模型不可比）。"""
        from evals.performance.measure import PerfAggregate, append_history, run_offline

        path = tmp_path / "h.jsonl"
        for lat in (1.0, 1.1, 1.3):
            agg = PerfAggregate(total=5, by_mode={}, avg_latency_s=lat)
            append_history(path, agg, model="other-model")
        result = run_offline([_trace(latency=2.0)], history_path=path, model="m")
        assert result["trend_alert"] is False
