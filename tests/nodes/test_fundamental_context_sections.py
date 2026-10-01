"""Task 8：基本面上下文注入估值快照与最新报告期快照（缺失时显式声明）。"""

from finance_agent.nodes.analysts import _build_fundamental_context


class TestContextValuationAndSnapshot:
    def test_valuation_and_snapshot_sections_present(self):
        state = {
            "valuation_snapshot": {
                "market_cap": 1910.23,
                "PE": None,
                "PE_ttm": 87.79,
                "PE_caliber": "derived_ttm",
                "PB": 15.02,
                "missing_reasons": [],
            },
            "latest_period_snapshot": {
                "报告日": "2026-06-30",
                "期类型": "中报",
                "毛利率(%)": 41.0,
            },
        }
        ctx = _build_fundamental_context(state)
        assert "估值快照（state 键 valuation_snapshot" in ctx
        assert "PE_caliber" in ctx and "derived_ttm" in ctx
        assert "最新报告期快照（state 键 latest_period_snapshot" in ctx
        assert "累计口径" in ctx

    def test_missing_sections_declared(self):
        ctx = _build_fundamental_context({})
        assert "估值数据缺失" in ctx
        assert "最新报告期快照缺失" in ctx
