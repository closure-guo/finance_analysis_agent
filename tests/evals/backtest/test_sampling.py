"""分层市场状态抽样测试：regime 判定 + 三 regime 覆盖（纯逻辑）。"""

import pandas as pd
import pytest
from evals.backtest.sampling import classify_regime, stratified_sample


def _index(total: float) -> pd.DataFrame:
    n = 60
    start = 100.0
    end = start * (1 + total)
    closes = [start + (end - start) * i / (n - 1) for i in range(n)]
    return pd.DataFrame(
        {
            "日期": [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)],
            "收盘": closes,
        }
    )


class TestRegime:
    def test_bull_bear_sideways(self):
        assert classify_regime(_index(0.30)) == "bull"
        assert classify_regime(_index(-0.30)) == "bear"
        assert classify_regime(_index(0.02)) == "sideways"

    def test_threshold_boundary(self):
        # 阈值 ±10% 邻域：其内 sideways，越过判单边
        # （恰好 ±10% 的浮点表示有 ~1e-17 噪声，不做精确边界断言）
        assert classify_regime(_index(0.0999)) == "sideways"
        assert classify_regime(_index(-0.0999)) == "sideways"
        assert classify_regime(_index(0.1001)) == "bull"
        assert classify_regime(_index(-0.1001)) == "bear"

    def test_empty_window_raises(self):
        with pytest.raises(ValueError, match="空窗口"):
            classify_regime(pd.DataFrame({"收盘": pd.Series(dtype=float)}))


class TestStratifiedSample:
    def test_three_regimes_ten_stocks(self):
        # 三段拼接的指数历史：上涨 + 下跌 + 震荡
        kline = pd.concat([_index(0.3), _index(-0.3), _index(0.0)], ignore_index=True)
        pool = [f"{600000 + i}" for i in range(40)]
        sample = stratified_sample(kline, pool, per_regime=10, window_days=55)
        regimes = {s["regime"] for s in sample}
        assert regimes == {"bull", "bear", "sideways"}
        for regime in regimes:
            assert sum(1 for s in sample if s["regime"] == regime) >= 10
        # 每个样本条目形如 {"code","regime","decision_date"}
        for s in sample:
            assert set(s) == {"code", "regime", "decision_date"}
            assert s["decision_date"][:2] == "20"

    def test_missing_regime_raises(self):
        pool = [f"{600000 + i}" for i in range(40)]
        with pytest.raises(ValueError, match="regime"):
            stratified_sample(_index(0.3), pool, per_regime=10, window_days=55)

    def test_insufficient_pool_raises(self):
        kline = pd.concat([_index(0.3), _index(-0.3), _index(0.0)], ignore_index=True)
        with pytest.raises(ValueError, match="标的池不足"):
            stratified_sample(kline, ["600000", "600001"], per_regime=10, window_days=55)

    def test_deterministic_given_seed(self):
        kline = pd.concat([_index(0.3), _index(-0.3), _index(0.0)], ignore_index=True)
        pool = [f"{600000 + i}" for i in range(40)]
        s1 = stratified_sample(kline, pool, per_regime=5, window_days=55, seed=7)
        s2 = stratified_sample(kline, pool, per_regime=5, window_days=55, seed=7)
        assert s1 == s2
