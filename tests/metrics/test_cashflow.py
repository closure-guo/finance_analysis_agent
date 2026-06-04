"""TDD tests for metrics/cashflow.py — 现金流健康 6 指标。

指标：
1. 经营现金流/净利润 — OCF / 净利润
2. FCF — OCF - CapEx
3. 资本支出/折旧 — CapEx / 折旧变动
4. 现金流覆盖比率 — FCF / (CapEx + 利息)
5. FCF 收益率 — FCF / 市值 (MVP 用营业收入代替市值)
6. 留存现金流比率 — (FCF - 股利) / FCF

fixture 手算（2024）：
- OCF=250, 净利润=170, CapEx=80, 折旧变动=20, 股利=50, 利息=20
- OCF/净利润 = 250/170 = 1.471
- FCF = 250 - 80 = 170
- CapEx/折旧 = 80/20 = 4.0
- 现金流覆盖 = 170 / (80+20) = 1.7
- FCF收益率(简化) = 170/1000 = 0.17 (用营业收入)
- 留存现金流 = (170-50)/170 = 0.706
"""

from math import isclose

from finance_agent.metrics.cashflow import calc_cashflow


class TestCalcCashflow:
    def test_returns_all_metrics(self, balance_sheet, income_statement, cash_flow, indicators):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        expected_keys = {
            "经营现金流/净利润",
            "FCF",
            "资本支出/折旧",
            "现金流覆盖比率",
            "FCF收益率",
            "留存现金流比率",
        }
        assert set(result.keys()) == expected_keys

    def test_each_metric_has_all_years(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        for name, values in result.items():
            assert set(values.keys()) == {"2024", "2023", "2022"}, f"{name} years mismatch"

    def test_ocf_to_net_income_2024(self, balance_sheet, income_statement, cash_flow, indicators):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        assert isclose(result["经营现金流/净利润"]["2024"], 250 / 170, rel_tol=1e-2)

    def test_fcf_2024(self, balance_sheet, income_statement, cash_flow, indicators):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        assert isclose(result["FCF"]["2024"], 250 - 80, rel_tol=1e-2)

    def test_capex_to_depreciation_2024(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        # CapEx=80, 折旧变动(2024-2023)=120-100=20
        assert isclose(result["资本支出/折旧"]["2024"], 80 / 20, rel_tol=1e-2)

    def test_cashflow_coverage_2024(self, balance_sheet, income_statement, cash_flow, indicators):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        # FCF=170, CapEx=80, 利息=20 → 170/(80+20) = 1.7
        assert isclose(result["现金流覆盖比率"]["2024"], 170 / 100, rel_tol=1e-2)

    def test_fcf_yield_2024(self, balance_sheet, income_statement, cash_flow, indicators):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        # FCF=170, 营业收入=1000 → 0.17
        assert isclose(result["FCF收益率"]["2024"], 170 / 1000, rel_tol=1e-2)

    def test_retained_cashflow_ratio_2024(
        self, balance_sheet, income_statement, cash_flow, indicators
    ):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        # (FCF - 股利) / FCF = (170-50)/170 = 0.706
        assert isclose(result["留存现金流比率"]["2024"], (170 - 50) / 170, rel_tol=1e-2)

    def test_fcf_2023(self, balance_sheet, income_statement, cash_flow, indicators):
        result = calc_cashflow(balance_sheet, income_statement, cash_flow)
        assert isclose(result["FCF"]["2023"], 220 - 70, rel_tol=1e-2)

    def test_zero_net_income(self):
        import pandas as pd

        bs = pd.DataFrame({"报告日": ["20241231"], "营业收入": [1000.0], "累计折旧": [100.0]})
        is_ = pd.DataFrame({"报告日": ["20241231"], "净利润": [0.0], "利息费用": [0.0]})
        cf = pd.DataFrame(
            {
                "报告日": ["20241231"],
                "经营活动产生的现金流量净额": [100.0],
                "购建固定资产、无形资产和其他长期资产所支付的现金": [50.0],
                "分配股利、利润或偿付利息所支付的现金": [30.0],
            }
        )
        result = calc_cashflow(bs, is_, cf)
        assert result["经营现金流/净利润"]["2024"] is None

    def test_fcf_growth_rate_in_growth_rates(self):
        """FCF 增长率应通过 growth_rates 传递给 LLM，而非由 LLM 自算。

        fixture: FCF(2024)=170, FCF(2023)=150
        growth = (170-150)/150 = 13.3%
        """
        from finance_agent.nodes.compute import _calc_growth_rates

        cfm = calc_cashflow(self._bs(), self._is(), self._cf())
        all_metrics = {"cashflow": cfm}
        years = sorted({y for v in cfm.values() for y in v}, reverse=True)
        gr = _calc_growth_rates(all_metrics, years)

        fcf_growth = gr.get("cashflow", {}).get("FCF")
        assert fcf_growth is not None
        expected = (170 - 150) / 150
        assert isclose(fcf_growth, expected, rel_tol=1e-2)

    def _bs(self):
        import pandas as pd

        return pd.DataFrame(
            {
                "报告日": ["20241231", "20231231", "20221231"],
                "营业收入": [1000.0, 900.0, 800.0],
                "累计折旧": [120.0, 100.0, 80.0],
            }
        )

    def _is(self):
        import pandas as pd

        return pd.DataFrame(
            {
                "报告日": ["20241231", "20231231", "20221231"],
                "净利润": [170.0, 153.0, 136.0],
                "利息费用": [20.0, 18.0, 16.0],
            }
        )

    def _cf(self):
        import pandas as pd

        return pd.DataFrame(
            {
                "报告日": ["20241231", "20231231", "20221231"],
                "经营活动产生的现金流量净额": [250.0, 220.0, 200.0],
                "购建固定资产、无形资产和其他长期资产所支付的现金": [80.0, 70.0, 60.0],
                "分配股利、利润或偿付利息所支付的现金": [50.0, 45.0, 40.0],
            }
        )
