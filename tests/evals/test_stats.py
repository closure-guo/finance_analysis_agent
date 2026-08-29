"""统计核心测试：确定性 seed 下 CI 数值可复现。"""

from evals.stats import (
    block_bootstrap_stat,
    cohen_kappa,
    paired_block_bootstrap_diff,
    paired_bootstrap_ci,
    sharpe,
)


class TestPairedBootstrap:
    def test_ci_excludes_zero_for_clear_gap(self):
        a = [0.9, 0.91, 0.89, 0.92, 0.9]
        b = [0.5, 0.49, 0.51, 0.5, 0.5]
        lo, hi = paired_bootstrap_ci(a, b, B=2_000, seed=7)
        assert lo > 0

    def test_ci_contains_zero_for_identical(self):
        a = [0.5, 0.6, 0.4]
        lo, hi = paired_bootstrap_ci(a, a, B=500, seed=7)
        assert lo <= 0.0 <= hi

    def test_deterministic_with_seed(self):
        a = [1.0, 2.0, 3.0, 4.0]
        b = [1.5, 1.0, 2.5, 2.0]
        assert paired_bootstrap_ci(a, b, B=500, seed=11) == paired_bootstrap_ci(
            a, b, B=500, seed=11
        )


class TestSharpe:
    def test_constant_returns_zero_vol_defined(self):
        # 恒定收益 std=0：返回 0.0 而非除零
        assert sharpe([0.01] * 10) == 0.0

    def test_positive_skew_positive_sharpe(self):
        r = [0.02] * 8 + [0.0, 0.0]
        assert sharpe(r) > 0


class TestBlockBootstrap:
    def test_stat_ci_brackets_point_estimate(self):
        series = [0.001 * ((i % 7) - 3) + 0.002 for i in range(200)]
        lo, hi = block_bootstrap_stat(series, sharpe, block_size=20, B=500, seed=3)
        assert lo <= sharpe(series) <= hi

    def test_paired_diff_ci(self):
        a = [0.002 + 0.0005 * ((i % 5) - 2) for i in range(120)]
        b = [0.0 for _ in range(120)]
        lo, hi = paired_block_bootstrap_diff(a, b, block_size=20, B=500, seed=3)
        assert lo <= hi


class TestCohenKappa:
    def test_perfect_agreement(self):
        labels = ["PASS", "FAIL", "UNVERIFIABLE", "PASS"]
        assert cohen_kappa(labels, labels) == 1.0

    def test_chance_agreement_near_zero(self):
        a = ["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"]
        b = ["PASS", "PASS", "PASS", "PASS", "FAIL", "FAIL"]
        kappa = cohen_kappa(a, b)
        assert -0.2 < kappa < 0.2

    def test_length_mismatch_raises(self):
        import pytest

        with pytest.raises(ValueError):
            cohen_kappa(["PASS"], ["PASS", "FAIL"])
