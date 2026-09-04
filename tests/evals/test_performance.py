"""add-latency-cost-regression：性能聚合/基线回归/趋势 测试（fixtures 离线）。"""

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
