"""TDD tests for metrics/risk.py — 风控指标计算。

指标：
1. 最大回撤（Max Drawdown）— 峰值到谷值的最大跌幅
2. 年化波动率（Volatility）— 日收益率标准差 × √252
3. Beta — 个股 vs 沪深300 的系统性风险
4. VaR(95%) — 95% 置信度下的单日最大损失

fixture K 线数据含明确回撤：10→15→11→16
  峰值 15（index 2），谷值 11（index 4）
  最大回撤 = (11-15)/15 = -26.67% → 0.2667
"""

from math import isclose

import pandas as pd

from finance_agent.metrics.risk import calc_risk


def _kline_with_drawdown() -> pd.DataFrame:
    """K 线数据含明确回撤：10→15→11→16。"""
    return pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-02", periods=7, freq="B"),
            "收盘": [10.0, 12.0, 15.0, 13.0, 11.0, 14.0, 16.0],
            "开盘": [10.0, 12.0, 15.0, 13.0, 11.0, 14.0, 16.0],
            "最高": [10.0, 12.0, 15.0, 13.0, 11.0, 14.0, 16.0],
            "最低": [10.0, 12.0, 15.0, 13.0, 11.0, 14.0, 16.0],
            "成交量": [1000] * 7,
        }
    )


def _benchmark_kline() -> pd.DataFrame:
    """沪深 300 基准 K 线。"""
    return pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-02", periods=7, freq="B"),
            "收盘": [3000.0, 3030.0, 3060.0, 3040.0, 3020.0, 3050.0, 3080.0],
        }
    )


class TestCalcRisk:
    """风控指标计算测试。"""

    def test_max_drawdown(self):
        """最大回撤 = (11-15)/15 ≈ 0.2667。"""
        kline = _kline_with_drawdown()
        result = calc_risk(kline)
        assert isclose(result["max_drawdown"], 0.2667, rel_tol=1e-2)

    def test_volatility_positive(self):
        """年化波动率为正数。"""
        kline = _kline_with_drawdown()
        result = calc_risk(kline)
        assert result["volatility"] > 0

    def test_beta_with_benchmark(self):
        """Beta：有个股和基准数据时返回 float。"""
        kline = _kline_with_drawdown()
        bench = _benchmark_kline()
        result = calc_risk(kline, bench)
        assert "beta" in result
        assert isinstance(result["beta"], float)

    def test_var_95_positive(self):
        """VaR(95%) 为正数（代表可能的最大损失）。"""
        kline = _kline_with_drawdown()
        result = calc_risk(kline)
        assert result["var_95"] > 0
