"""绩效四指标测试：CR / ARR / Sharpe / MDD（纯逻辑，无 IO）。"""

from evals.backtest.performance import perf_metrics


class TestPerfMetrics:
    def test_known_values(self):
        # 100 日每日 +1%：CR = 1.01^100 - 1 ≈ 1.7048；MDD = 0
        # 注：常数序列 std=0，Task 4 evals.stats.sharpe 冻结为安全返回 0.0
        returns = [0.01] * 100
        m = perf_metrics(returns)
        assert abs(m["CR"] - (1.01**100 - 1)) < 1e-9
        assert m["MDD"] == 0.0
        assert m["Sharpe"] == 0.0
        assert m["ARR"] > m["CR"]

    def test_varying_positive_returns_positive_sharpe(self):
        # 非常数正收益序列 → Sharpe > 0（年化口径，rf=0）
        returns = [0.01, 0.02, 0.005, 0.015] * 25
        m = perf_metrics(returns)
        assert m["Sharpe"] > 0
        assert m["ARR"] > 0
        assert m["MDD"] >= 0.0

    def test_drawdown_from_peak(self):
        returns = [0.1, -0.2, 0.0]
        m = perf_metrics(returns)
        # 峰值 1.1 → 谷 1.1×0.8=0.88 → MDD = (1.1-0.88)/1.1 = 0.22/1.1 = 0.2
        # （复利口径；brief 注释 0.2/1.1 系非复利心算笔误）
        assert abs(m["MDD"] - 0.22 / 1.1) < 1e-9

    def test_empty_returns_zeroed(self):
        m = perf_metrics([])
        assert m == {"CR": 0.0, "ARR": 0.0, "Sharpe": 0.0, "MDD": 0.0}

    def test_single_return(self):
        m = perf_metrics([0.05])
        assert abs(m["CR"] - 0.05) < 1e-12
        # 单点无波动 → Sharpe 0（安全默认，与 evals.stats.sharpe 一致）
        assert m["Sharpe"] == 0.0

    def test_total_loss_capped(self):
        # 单日 -100%：财富归零，ARR 不做 0 的分数幂
        m = perf_metrics([-1.0])
        assert m["CR"] == -1.0
        assert m["ARR"] == -1.0
        assert m["MDD"] == 1.0
