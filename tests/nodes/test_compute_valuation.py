import pandas as pd

from finance_agent.nodes.compute import _build_valuation_snapshot, _derive_pe_ttm

SNAP_H1 = {
    "报告日": "2026-06-30",
    "期类型": "中报",
    "归母净利润(累计)": 13.43,
    "上年同期归母净利润": 0.94,
    "营业总收入(累计)": 29.13,
    "毛利率(%)": 41.0,
}


class TestDerivePeTtm:
    def test_ttm_blended_from_h1(self):
        # 9.27 - 0.94 + 13.43 = 21.76；1910.23/21.76 = 87.7863 → round2 = 87.79
        pe, reason = _derive_pe_ttm(1910.23, 9.27, SNAP_H1)
        assert pe == 87.79
        assert reason is None

    def test_annual_snapshot_takes_annual_value(self):
        snap = {"报告日": "2025-12-31", "期类型": "年报", "归母净利润(累计)": 9.27}
        pe, reason = _derive_pe_ttm(92.7, 9.27, snap)
        assert pe == 10.0

    def test_missing_market_cap_returns_none_with_reason(self):
        pe, reason = _derive_pe_ttm(None, 9.27, SNAP_H1)
        assert pe is None and "market_cap" in reason

    def test_missing_snapshot_returns_none_not_static_fallback(self):
        pe, reason = _derive_pe_ttm(1910.23, 9.27, {})
        assert pe is None and "快照" in reason

    def test_negative_ttm_returns_none(self):
        snap = {
            "报告日": "2026-06-30",
            "期类型": "中报",
            "归母净利润(累计)": -30.0,
            "上年同期归母净利润": 0.94,
        }
        pe, reason = _derive_pe_ttm(100.0, 9.27, snap)
        assert pe is None and "非正" in reason

    def test_non_positive_market_cap_returns_reason(self):
        # 审查 F2：market_cap 非 None 但 <= 0（0 / -5）→ (None, reason 含 market_cap)
        for bad in (0, -5.0):
            pe, reason = _derive_pe_ttm(bad, 9.27, SNAP_H1)
            assert pe is None
            assert "market_cap" in reason

    def test_non_positive_annual_np_returns_reason(self):
        # 审查 F2：annual_np 非 None 但 <= 0 → (None, reason 含 年报归母净利润)
        pe, reason = _derive_pe_ttm(1910.23, 0, SNAP_H1)
        assert pe is None
        assert "年报归母净利润" in reason

    def test_nan_market_cap_returns_none(self):
        # 审查 F1：东财 spot 停牌股 总市值=NaN 直达 quote，NaN<=0 恒 False 不得产出 NaN PE
        pe, reason = _derive_pe_ttm(float("nan"), 9.27, SNAP_H1)
        assert pe is None
        assert reason

    def test_nan_snapshot_cum_np_returns_none(self):
        # 审查 F1：快照累计归母净利 NaN → ttm=NaN，NaN<=0 恒 False 不得产出 NaN PE
        snap = {
            "报告日": "2026-06-30",
            "期类型": "中报",
            "归母净利润(累计)": float("nan"),
            "上年同期归母净利润": 0.94,
        }
        pe, reason = _derive_pe_ttm(1910.23, 9.27, snap)
        assert pe is None
        assert reason is not None


class TestBuildValuationSnapshot:
    def _state(self, quote):
        inc = pd.DataFrame({"报告日": ["20251231", "20241231"], "归母净利润": [9.27e8, 6.88e8]})
        return {"stock_quote": quote, "income_statement": inc, "latest_period_snapshot": SNAP_H1}

    def test_assembly_with_derived_ttm(self):
        vs = _build_valuation_snapshot(self._state({"market_cap": 1910.23, "PB": 15.02}))
        assert vs["PE"] is None
        assert vs["PE_ttm"] == 87.79
        assert vs["PE_caliber"] == "derived_ttm"
        assert vs["market_cap"] == 1910.23
        assert vs["PB"] == 15.02
        assert vs["missing_reasons"] == []

    def test_static_pe_wins_caliber_static(self):
        vs = _build_valuation_snapshot(
            self._state({"market_cap": 1910.23, "PE": 95.0, "PB": 15.02})
        )
        assert vs["PE"] == 95.0 and vs["PE_caliber"] == "static"

    def test_all_missing_reasons_listed(self):
        vs = _build_valuation_snapshot(self._state({}))
        assert vs["PE_caliber"] is None
        assert any("market_cap" in r for r in vs["missing_reasons"])

    def test_nan_quote_values_treated_as_missing(self):
        # 审查 F1 装配层：static PE=NaN 不得标 static 口径、NaN 市值视同缺失
        vs = _build_valuation_snapshot(
            self._state({"market_cap": float("nan"), "PE": float("nan")})
        )
        assert vs["PE"] is None
        assert vs["PE_ttm"] is None
        assert vs["PE_caliber"] is None
        assert vs["market_cap"] is None
        assert any("market_cap" in r for r in vs["missing_reasons"])
