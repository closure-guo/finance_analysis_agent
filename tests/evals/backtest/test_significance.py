"""显著性模块测试：sanity 拦截 + block bootstrap 块长敏感性。"""

from evals.backtest.significance import block_length_sensitivity, validate_sanity


class TestSanityGate:
    def test_high_sharpe_without_note_invalid(self):
        assert validate_sanity(3.5, None) == "invalid"

    def test_high_sharpe_with_note_valid(self):
        assert validate_sanity(3.5, "样本期 2019-2024 横跨牛熊；MDD 18%；月度换手") == "valid"

    def test_normal_sharpe_valid_without_note(self):
        assert validate_sanity(1.2, None) == "valid"

    def test_boundary_sharpe_not_flagged(self):
        # 恰好 3.0 不触发（严格大于才拦截）
        assert validate_sanity(3.0, None) == "valid"

    def test_blank_note_counts_as_missing(self):
        assert validate_sanity(3.5, "   ") == "invalid"


class TestSensitivity:
    def test_reports_multiple_block_lengths(self):
        returns = [0.001 * ((i % 9) - 4) + 0.0015 for i in range(200)]
        out = block_length_sensitivity(returns, B=300, seed=1)
        assert set(out) == {"10", "20", "40"}
        for ci in out.values():
            assert ci[0] <= ci[1]

    def test_custom_blocks(self):
        returns = [0.002, -0.001, 0.003, -0.002, 0.001] * 40
        out = block_length_sensitivity(returns, blocks=(5, 15), B=200, seed=3)
        assert set(out) == {"5", "15"}

    def test_reproducible_given_seed(self):
        returns = [((i % 7) - 3) * 0.001 + 0.0005 for i in range(150)]
        a = block_length_sensitivity(returns, B=150, seed=9)
        b = block_length_sensitivity(returns, B=150, seed=9)
        assert a == b
