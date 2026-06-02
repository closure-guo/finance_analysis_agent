"""TDD tests for metrics/profitability.py — 盈利 5 指标。

指标：
1. 毛利率（%）— AKShare 预计算
2. 净利率（%）— AKShare 预计算
3. ROE（%）— AKShare 预计算
4. ROA（%）— AKShare 预计算
5. ROIC（%）— 自算 = NOPAT / 投入资本

fixture 数据手算验证（2024）：
- 毛利率 = (1000-600)/1000 = 40%
- 净利率 = 170/1000 = 17%
- ROE = 170/600 = 28.33%
- ROA = 170/1000 = 17%
- ROIC:
  - NOPAT = 净利润*(1-税率调整) ≈ EBIT*(1-税率) = 200*(1-15%) = 170
  - 投入资本 = 所有者权益 + 有息负债 = 600 + 180 = 780
  - ROIC = 170/780 = 21.79%
"""

from math import isclose

from finance_agent.metrics.profitability import calc_profitability


class TestCalcProfitability:
    def test_returns_all_metrics(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        expected_keys = {"毛利率", "净利率", "ROE", "ROA", "ROIC"}
        assert set(result.keys()) == expected_keys

    def test_each_metric_has_all_years(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        for name, values in result.items():
            assert set(values.keys()) == {"2024", "2023", "2022"}, f"{name} years mismatch"

    def test_gross_margin_2024(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        assert isclose(result["毛利率"]["2024"], 40.0, rel_tol=1e-2)

    def test_net_margin_2024(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        assert isclose(result["净利率"]["2024"], 17.0, rel_tol=1e-2)

    def test_roe_2024(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        # ROE = 净利润 / 所有者权益 = 170/600 ≈ 28.33%
        assert isclose(result["ROE"]["2024"], 170 / 600 * 100, rel_tol=1e-2)

    def test_roa_2024(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        assert isclose(result["ROA"]["2024"], 17.0, rel_tol=1e-2)

    def test_roic_2024(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        # ROIC = NOPAT / 投入资本
        # NOPAT = EBIT*(1-税率) = 220 * (1 - 30/200) = 220 * 0.85 = 187
        # 投入资本 = 所有者权益 + 有息负债 = 600 + 180 = 780
        # ROIC = 187 / 780 * 100 ≈ 23.97%
        tax_rate = 30.0 / 200.0
        nopat = 220.0 * (1 - tax_rate)
        invested_capital = 600.0 + 180.0
        expected = nopat / invested_capital * 100
        assert isclose(result["ROIC"]["2024"], expected, rel_tol=1e-2)

    def test_roe_2023(self, balance_sheet, income_statement, indicators):
        result = calc_profitability(balance_sheet, income_statement, indicators)
        assert isclose(result["ROE"]["2023"], 153 / 550 * 100, rel_tol=1e-2)

    def test_zero_revenue(self):
        """营业收入为零时，毛利率和净利率应为 None。"""
        import pandas as pd

        bs = pd.DataFrame(
            {
                "报告日": ["20241231"],
                "所有者权益(或股东权益)合计": [500.0],
                "短期借款": [0.0],
                "长期借款": [0.0],
                "应付债券": [0.0],
                "一年内到期的非流动负债": [0.0],
            }
        )
        is_ = pd.DataFrame(
            {
                "报告日": ["20241231"],
                "营业收入": [0.0],
                "营业成本": [0.0],
                "净利润": [0.0],
                "利润总额": [0.0],
                "所得税费用": [0.0],
                "利息费用": [0.0],
            }
        )
        ind = pd.DataFrame(
            {
                "日期": ["2024-12-31"],
                "销售毛利率(%)": [None],
                "销售净利率(%)": [None],
                "净资产收益率(%)": [None],
                "总资产净利润率(%)": [None],
            }
        )
        result = calc_profitability(bs, is_, ind)
        assert result["毛利率"]["2024"] is None
        assert result["净利率"]["2024"] is None
