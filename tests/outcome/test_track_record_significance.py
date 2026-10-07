"""add-prediction-pool-integrity Task 5:IC/ICIR/蒙特卡洛零模型纯函数。"""

import logging
import random

import pytest

from finance_agent.outcome.track_record.significance import (
    _draw_group_symbols,
    excess_quantile,
    icir,
    monthly_ic,
    simulate_random_excess,
)


class TestMonthlyIC:
    def test_ic_counts_long_short_two_state(self):
        """方向 IC 只计 long/short 的 resolved_win/loss；neutral 与 avoidance 行不进分子分母。"""
        rows = [
            {"resolved_at": "2026-11-03", "status": "resolved_win", "direction": "long"},
            {"resolved_at": "2026-11-04", "status": "resolved_loss", "direction": "short"},
            {"resolved_at": "2026-11-05", "status": "resolved_neutral", "direction": "long"},
            {"resolved_at": "2026-11-06", "status": "avoidance", "direction": "neutral"},
        ]
        series = monthly_ic(rows)
        assert len(series) == 1
        s = series[0]
        assert s["month"] == "2026-11" and s["wins"] == 1 and s["losses"] == 1
        assert s["ic"] == 0.5 and s["sample"] == 2 and s["insufficient"] is True

    def test_months_sorted_ascending(self):
        """跨月分组按结算月升序返回。"""
        rows = [
            {"resolved_at": "2026-12-01", "status": "resolved_win", "direction": "long"},
            {"resolved_at": "2026-11-02", "status": "resolved_loss", "direction": "long"},
        ]
        assert [s["month"] for s in monthly_ic(rows)] == ["2026-11", "2026-12"]

    def test_avoidance_series_separate_from_direction_ic(self):
        """回避类单独成列（kind="avoidance"），不混入方向 IC。"""
        rows = [
            {"resolved_at": "2026-11-05", "status": "avoidance_win", "direction": "neutral"},
            {"resolved_at": "2026-11-06", "status": "avoidance_loss", "direction": "neutral"},
            {"resolved_at": "2026-11-03", "status": "resolved_win", "direction": "long"},
        ]
        assert monthly_ic(rows, kind="direction")[0]["wins"] == 1  # 回避行不进方向 IC
        av = monthly_ic(rows, kind="avoidance")
        assert av[0]["wins"] == 1 and av[0]["losses"] == 1 and av[0]["ic"] == 0.5

    def test_avoidance_db_shape_status_column(self):
        """DB 真实形状：status='avoidance'（终态）+ 独立 avoidance_status 列，能正确聚合。"""
        rows = [
            {
                "resolved_at": "2026-11-05",
                "status": "avoidance",
                "avoidance_status": "avoidance_win",
                "direction": "neutral",
            },
            {
                "resolved_at": "2026-11-06",
                "status": "avoidance",
                "avoidance_status": "avoidance_loss",
                "direction": "neutral",
            },
        ]
        av = monthly_ic(rows, kind="avoidance")
        assert len(av) == 1
        assert av[0]["wins"] == 1 and av[0]["losses"] == 1 and av[0]["ic"] == 0.5


class TestICIR:
    def test_icir_returns_none_below_min_periods(self):
        """有效期数不足 6 期 → None。"""
        series = [{"ic": 0.6, "insufficient": False}] * 5
        assert icir(series) is None

    def test_icir_excludes_insufficient_periods(self):
        """样本不足期被剔除后不足 6 期 → None。"""
        series = [{"ic": 0.6, "insufficient": False}] * 5 + [{"ic": 0.9, "insufficient": True}]
        assert icir(series) is None

    def test_icir_population_std_six_periods(self):
        """6 期有效序列计算总体标准差 ICIR。"""
        series = [{"ic": 0.5 + 0.01 * i, "insufficient": False} for i in range(6)]
        value = icir(series)
        assert value is not None and value > 0


class TestMonteCarlo:
    UNIVERSE = ["600519", "000001", "600030", "601818", "300750"]

    def _closes(self):
        return {
            s: {"2026-11-03": 10.0, "2026-12-01": 10.0 + i * 0.1}
            for i, s in enumerate(self.UNIVERSE)
        }

    def test_monte_carlo_exposure_aligned_and_reproducible(self):
        """敞口对齐：模拟注数与真实组合每归属日每方向一致；同种子结果复现。"""
        kwargs: dict = {
            "universe": self.UNIVERSE,
            "long_counts": {"2026-11-03": 2},
            "short_counts": {"2026-11-03": 1},
            "closes": self._closes(),
            "entry_map": {"2026-11-03": "2026-11-03"},
            "exit_date": "2026-12-01",
            "benchmark_closes": {"2026-11-03": 100.0, "2026-12-01": 96.0},
            "n_sims": 200,
            "seed": 42,
        }
        sims = simulate_random_excess(**kwargs)
        assert len(sims) == 200
        # 复现性：同种子同分布
        sims2 = simulate_random_excess(**kwargs)
        assert sims == sims2

    def test_per_slot_benchmark_excess_differs_by_entry_day(self):
        """per-slot 基准超额：每槽减自己入场档的基准收益（T+20 槽位入场日不同、同期基准不同）。

        两日槽位原始收益相同（10.0→11.0 = +10%），但 D1/D2 的基准收益不同
        （100→103 = +3%；102→103 ≈ +0.98%），注数比 2:1——期望 = 10% − 按注数加权
        的逐槽基准均值。组合层减单一 benchmark_return 的旧实现无法表达该差值。
        """
        universe = ["600519", "000001"]
        closes = {
            "600519": {
                "2026-11-03": 10.0,
                "2026-11-04": 10.0,
                "2026-12-01": 11.0,
            },
            "000001": {
                "2026-11-03": 10.0,
                "2026-11-04": 10.0,
                "2026-12-01": 11.0,
            },
        }
        benchmark_closes = {
            "2026-11-03": 100.0,
            "2026-11-04": 102.0,
            "2026-12-01": 103.0,
        }
        sims = simulate_random_excess(
            universe=universe,
            long_counts={"2026-11-03": 2, "2026-11-04": 1},
            short_counts={},
            closes=closes,
            entry_map={"2026-11-03": "2026-11-03", "2026-11-04": "2026-11-04"},
            exit_date="2026-12-01",
            benchmark_closes=benchmark_closes,
            n_sims=50,
            seed=42,
        )
        bench_d1 = 103.0 / 100.0 - 1.0
        bench_d2 = 103.0 / 102.0 - 1.0
        expected = 0.1 - (2 * bench_d1 + bench_d2) / 3
        assert len(sims) == 50
        assert all(s == pytest.approx(expected) for s in sims)

    def test_quantile_conservative_p_value(self):
        """右尾定位含真实读数自身：p=(greater+1)/(n+1) 保守口径。"""
        q = excess_quantile(0.10, [0.01, 0.02, 0.03])
        assert q["n_sims"] == 3 and q["quantile"] == 1.0 and q["p_value"] == 0.25


class TestWithoutReplacement:
    """零模型无放回口径（裁决：同 (归属日, 方向) 内无放回，对齐日主唯一性）。"""

    UNIVERSE = ["600519", "000001", "600030", "601818", "300750"]

    def test_group_draw_no_duplicates_within_direction(self):
        """注数 3、池 5：单次组抽取内同方向 symbol 无重复（固定种子重放 100 次）。"""
        rng = random.Random(42)  # noqa: S311  固定种子重放抽样序列，非密码用途
        for _ in range(100):
            syms, fell_back = _draw_group_symbols(rng, self.UNIVERSE, 3)
            assert fell_back is False
            assert len(syms) == 3 and len(set(syms)) == 3

    def test_group_draw_falls_back_when_pool_too_small(self):
        """注数 > 池大小（理论不可达）：回退有放回，不抛异常、返回注数个标的。"""
        rng = random.Random(42)  # noqa: S311  固定种子复现回退路径，非密码用途
        syms, fell_back = _draw_group_symbols(rng, ["600519", "000001"], 3)
        assert fell_back is True and len(syms) == 3

    def test_pool_too_small_logs_warning_before_return(self, caplog):
        """走公开 API 触发回退：返回前 log warning，不抛异常，仍返回 n_sims 条模拟。"""
        closes = {
            "600519": {"2026-11-03": 10.0, "2026-12-01": 11.0},
            "000001": {"2026-11-03": 10.0, "2026-12-01": 9.0},
        }
        with caplog.at_level(logging.WARNING):
            sims = simulate_random_excess(
                universe=["600519", "000001"],
                long_counts={"2026-11-03": 3},
                short_counts={},
                closes=closes,
                entry_map={"2026-11-03": "2026-11-03"},
                exit_date="2026-12-01",
                benchmark_closes={"2026-11-03": 100.0, "2026-12-01": 100.0},
                n_sims=5,
                seed=42,
            )
        assert len(sims) == 5
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings and "回退" in warnings[0].message

    def test_empty_pool_returns_empty_with_warning(self, caplog):
        """pool 为空（universe 无一含行情）：不抛 IndexError，warning + 返回空列表。"""
        closes = {"000001": {"2026-11-03": 10.0, "2026-12-01": 9.0}}  # universe 标的不在 closes
        with caplog.at_level(logging.WARNING):
            sims = simulate_random_excess(
                universe=["600519"],
                long_counts={"2026-11-03": 2},
                short_counts={},
                closes=closes,
                entry_map={"2026-11-03": "2026-11-03"},
                exit_date="2026-12-01",
                benchmark_closes={"2026-11-03": 100.0, "2026-12-01": 100.0},
                n_sims=5,
                seed=42,
            )
        assert sims == []
        assert any(r.levelno == logging.WARNING for r in caplog.records)
