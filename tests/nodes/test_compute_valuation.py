import pandas as pd

from finance_agent.nodes.compute import _build_valuation_snapshot, _derive_pe_ttm, _try_garp

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


class TestTryGarp:
    """_try_garp 接线：PE 取自 valuation_snapshot（口径已选好），行业 PE 来自 state.industry_pe。"""

    @staticmethod
    def _deps(roe=0.20, debt_pct=45.0):
        return (
            {"ROE": {"2024": roe}},
            {"资产负债率": {"2024": debt_pct}},
        )

    def test_pe_from_snapshot_with_industry_pe_passes(self):
        # PE=20 < 行业平均 25，growth/ROE/debt 均达标 → 全过；static 口径随 details 记录
        profitability, solvency = self._deps()
        vs = {"PE": 20.0, "PE_ttm": None, "PE_caliber": "static"}
        result = _try_garp(vs, profitability, solvency, None, 0.25, "2024", industry_pe_avg=25.0)
        assert result["pass"] is True
        assert result["failures"] == []
        assert "PE_missing" not in result["details"]
        assert result["details"]["PE_caliber"] == "static"

    def test_pe_ttm_fallback_when_static_missing(self):
        # 快照 static PE 缺失 → 回落 PE_ttm（Task 5 已选好口径）
        profitability, solvency = self._deps()
        vs = {"PE": None, "PE_ttm": 20.0, "PE_caliber": "derived_ttm"}
        result = _try_garp(vs, profitability, solvency, None, 0.25, "2024", industry_pe_avg=25.0)
        assert result["pass"] is True
        assert result["details"]["PE"] == 20.0
        assert result["details"]["PE_caliber"] == "derived_ttm"

    def test_missing_industry_pe_honest_not_fake_failure(self):
        # 无行业 PE → 诚实缺数分桶，不再恒定假性失败 PE 项
        profitability, solvency = self._deps()
        vs = {"PE": 20.0, "PE_ttm": None}
        result = _try_garp(vs, profitability, solvency, None, 0.25, "2024", industry_pe_avg=None)
        assert result["pass"] is False
        assert "行业平均 PE 数据缺失（未参与比较）" in result["failures"]
        assert "PE >= 行业平均" not in result["failures"]
        assert result["details"]["PE_missing"] is True

    def test_nan_industry_pe_avg_treated_as_missing(self):
        # 复审 F2：avg_pe=NaN 直达时 NaN 比较恒 False，会把行业 PE 缺数伪装成 PE 达标——视同缺失
        profitability, solvency = self._deps()
        vs = {"PE": None, "PE_ttm": 87.8, "PE_caliber": "derived_ttm"}
        result = _try_garp(
            vs, profitability, solvency, None, 0.25, "2024", industry_pe_avg=float("nan")
        )
        assert result["pass"] is False
        assert "行业平均 PE 数据缺失（未参与比较）" in result["failures"]
        assert "PE >= 行业平均" not in result["failures"]
        assert result["details"]["PE_missing"] is True

    def test_pe_caliber_recorded_on_real_comparison_failure(self):
        # spec scenario「有 PE_ttm 时 GARP 正常比较」：PE_ttm=87.8 vs 行业平均 45
        # → 真实比较失败，details SHALL 记录 PE=87.8 与口径 derived_ttm
        profitability, solvency = self._deps()
        vs = {"PE": None, "PE_ttm": 87.8, "PE_caliber": "derived_ttm"}
        result = _try_garp(vs, profitability, solvency, None, 0.25, "2024", industry_pe_avg=45.0)
        assert result["pass"] is False
        assert "PE >= 行业平均" in result["failures"]
        assert result["details"]["PE"] == 87.8
        assert result["details"]["PE_caliber"] == "derived_ttm"
        assert "PE_missing" not in result["details"]

    def test_real_comparison_failure_via_industry_pe(self):
        # PE=30 >= 行业平均 25 → 真实比较失败文案
        profitability, solvency = self._deps()
        vs = {"PE": 30.0, "PE_ttm": None}
        result = _try_garp(vs, profitability, solvency, None, 0.25, "2024", industry_pe_avg=25.0)
        assert result["pass"] is False
        assert "PE >= 行业平均" in result["failures"]
        assert "PE_missing" not in result["details"]


class TestRelativeValuationWithDerivedPe:
    """Task 7：quote PE 缺失（东财封锁走百度回退）时相对估值用 PE_ttm，不再整体跳过。"""

    def test_relative_uses_ttm_when_static_missing(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        from finance_agent.nodes.compute import compute_metrics

        inc = income_statement.rename(columns={"归属于母公司所有者的净利润": "归母净利润"})
        inc["归母净利润"] = [9.27e8, 6.88e8, 6.34e8]
        state = {
            "balance_sheet": balance_sheet,
            "income_statement": inc,
            "cash_flow_statement": cash_flow,
            "financial_indicators": indicators,
            "stock_quote": {"market_cap": 1910.23, "PB": 15.02},
            "industry_info": {},
            "latest_period_snapshot": SNAP_H1,
            # _build_peers_list 契约为 DataFrame（fetch.fetch_peer_data 产出形状）
            "peer_financials": pd.DataFrame(
                {
                    "name": ["中微公司", "北方华创"],
                    "PE": [60.0, 50.0],
                    "PB": [10.0, 9.0],
                }
            ),
        }
        result = compute_metrics(state)
        rel = result["relative_valuation"]["PE"]
        # TTM = 9.27-0.94+13.43 = 21.76；1910.23/21.76 = 87.79；同业均值 55 → overvalued
        assert rel["target"] == 87.79
        assert rel["peer_avg"] == 55.0
        assert rel["conclusion"] == "overvalued"
