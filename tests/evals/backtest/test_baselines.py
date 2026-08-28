"""规则基线测试：Buy-and-Hold / MACD / KDJ / RSI（复用 metrics/technical.py）。"""

import pandas as pd
import pytest
from evals.backtest.baselines import baseline_positions, strategy_returns


def _kline(n: int = 120, drift: float = 0.05) -> pd.DataFrame:
    close = [10.0 * (1 + drift) ** i for i in range(n)]
    return pd.DataFrame(
        {
            "日期": [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)],
            "开盘": close,
            "收盘": close,
            "最高": [c * 1.01 for c in close],
            "最低": [c * 0.99 for c in close],
            "成交量": [100.0] * n,
        }
    )


class TestBaselines:
    def test_buy_hold_always_long(self):
        pos = baseline_positions(_kline(), "buy_hold")
        assert (pos == 1).all()

    def test_macd_trend_following(self):
        # 单边上涨 → MACD DIF>DEA → 大部分时间持仓
        pos = baseline_positions(_kline(), "macd")
        assert pos.iloc[-1] == 1
        assert pos.mean() > 0.5

    def test_kdj_shape(self):
        kline = _kline()
        pos = baseline_positions(kline, "kdj")
        assert len(pos) == len(kline)
        assert set(pos.unique()) <= {0.0, 1.0}

    def test_rsi_saturates_to_flat_in_strong_trend(self):
        # 强单边上涨 → RSI 长期 >70 超买 → 空仓（反转策略语义）
        pos = baseline_positions(_kline(), "rsi")
        assert pos.iloc[-1] == 0

    def test_positions_length_matches_kline(self):
        kline = _kline()
        for strat in ("buy_hold", "macd", "kdj", "rsi"):
            assert len(baseline_positions(kline, strat)) == len(kline)

    def test_strategy_returns_length_matches(self):
        kline = _kline()
        pos = baseline_positions(kline, "rsi")
        rets = strategy_returns(kline, pos)
        assert len(rets) == len(kline) - 1  # 首日无前仓收益

    def test_strategy_returns_no_lookahead(self):
        # T-1 信号 T 生效：当日收益只乘以前一日仓位
        kline = _kline(n=5)
        close = kline["收盘"].astype(float).tolist()
        pos = pd.Series([0.0, 1.0, 1.0, 0.0, 0.0])
        rets = strategy_returns(kline, pos)
        expected = [
            0.0,  # 首日无前仓
            close[2] / close[1] - 1,  # 前日仓 1
            close[3] / close[2] - 1,  # 前日仓 1
            0.0,  # 前日仓 0 → 当日涨幅不计
        ]
        assert rets == pytest.approx(expected)

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            baseline_positions(_kline(), "nope")
