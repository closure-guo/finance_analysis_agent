"""TDD tests for metrics/technical.py — 技术指标计算。

指标：
1. MA（5/10/20/60）— 简单移动平均
2. MACD — EMA12 - EMA26, signal=EMA9, histogram
3. RSI（14）— 相对强弱指数
4. BOLL（20, 2σ）— 布林带
5. KDJ（9）— 随机指标

fixture K 线数据（10 天，收盘价 11→20 等差递增）：
  日期        收盘
  2024-01-02  11
  2024-01-03  12
  ...
  2024-01-15  20

手算验证：
  MA5[4] = (11+12+13+14+15)/5 = 13.0  ← 第 5 天
  MA5[5] = (12+13+14+15+16)/5 = 14.0  ← 第 6 天
"""

from math import isclose

import pandas as pd

from finance_agent.metrics.technical import calc_technical


def _kline_fixture() -> pd.DataFrame:
    """10 天 K 线数据，收盘价 11→20 等差递增。"""
    return pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-02", periods=10, freq="B"),
            "开盘": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
            "收盘": [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0],
            "最高": [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0],
            "最低": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
            "成交量": [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900],
        }
    )


def _kline_30d() -> pd.DataFrame:
    """30 天 K 线数据，收盘价 11→40 等差递增。"""
    return pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-02", periods=30, freq="B"),
            "开盘": [float(i) for i in range(10, 40)],
            "收盘": [float(i) for i in range(11, 41)],
            "最高": [float(i) for i in range(11, 41)],
            "最低": [float(i) for i in range(10, 40)],
            "成交量": [1000 + i * 100 for i in range(30)],
        }
    )


class TestCalcTechnical:
    """技术指标计算测试。"""

    def test_ma5_values(self):
        """MA5：第 5 天起有值，手算验证。"""
        kline = _kline_fixture()
        result = calc_technical(kline)
        ma5 = result["MA"]["5"]
        # 前 4 天无值
        assert ma5[:4] == [None, None, None, None]
        # 第 5 天: (11+12+13+14+15)/5 = 13.0
        assert isclose(ma5[4], 13.0, rel_tol=1e-6)
        # 第 6 天: (12+13+14+15+16)/5 = 14.0
        assert isclose(ma5[5], 14.0, rel_tol=1e-6)

    def test_macd_structure_and_histogram(self):
        """MACD：DIF/DEA/histogram 存在，histogram = 2*(DIF-DEA)。"""
        kline = _kline_fixture()
        result = calc_technical(kline)
        macd = result["MACD"]
        assert set(macd.keys()) == {"DIF", "DEA", "histogram"}
        n = len(kline)
        for key in ("DIF", "DEA", "histogram"):
            assert len(macd[key]) == n
        # 验证 histogram = 2 * (DIF - DEA)（非 None 处）
        for i in range(n):
            dif, dea, hist = macd["DIF"][i], macd["DEA"][i], macd["histogram"][i]
            if dif is not None and dea is not None and hist is not None:
                assert isclose(hist, 2 * (dif - dea), rel_tol=1e-4)

    def test_rsi_structure_and_range(self):
        """RSI14：值在 [0, 100] 范围内，前 14 天为 None。"""
        kline = _kline_30d()
        result = calc_technical(kline)
        rsi = result["RSI"]["14"]
        n = len(kline)
        assert len(rsi) == n
        # 前 14 天无值
        assert rsi[:14] == [None] * 14
        # 有值的部分在 0-100 范围内（持续上涨 → RSI 接近 100）
        for v in rsi[14:]:
            assert v is not None
            assert 0 <= v <= 100

    def test_boll_structure_and_band_order(self):
        """BOLL20：upper >= middle >= lower。"""
        kline = _kline_30d()
        result = calc_technical(kline)
        boll = result["BOLL"]
        assert set(boll.keys()) == {"upper", "middle", "lower"}
        n = len(kline)
        for key in ("upper", "middle", "lower"):
            assert len(boll[key]) == n
        # 前 19 天无值
        assert boll["middle"][:19] == [None] * 19
        # 有值处 upper >= middle >= lower
        for i in range(19, n):
            u, m, lo = boll["upper"][i], boll["middle"][i], boll["lower"][i]
            assert u is not None and m is not None and lo is not None
            assert u >= m >= lo

    def test_kdj_structure_and_j_formula(self):
        """KDJ9：J = 3*K - 2*D。"""
        kline = _kline_fixture()
        result = calc_technical(kline)
        kdj = result["KDJ"]
        assert set(kdj.keys()) == {"K", "D", "J"}
        n = len(kline)
        for key in ("K", "D", "J"):
            assert len(kdj[key]) == n
        # 验证 J = 3K - 2D（非 None 处）
        for i in range(n):
            k, d, j = kdj["K"][i], kdj["D"][i], kdj["J"][i]
            if k is not None and d is not None and j is not None:
                assert isclose(j, 3 * k - 2 * d, rel_tol=1e-4)
