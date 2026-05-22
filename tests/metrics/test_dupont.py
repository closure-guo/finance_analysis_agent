"""TDD tests for metrics/dupont.py — 杜邦 3 层分解。

杜邦分解：
L1: ROE = 净利率 × 总资产周转率 × 权益乘数
L2: 净利率 → 毛利率-费用率；周转率 → 存货/应收/固定资产；权益乘数 → 负债结构
L3: 费用率 → 销售费用率 + 管理费用率 + 研发费用率 + 财务费用率

fixture 手算（2024）：
- 净利率 = 170/1000 = 0.17
- 总资产周转率 = 1000/1000 = 1.0
- 权益乘数 = 1000/600 = 1.667
- ROE = 0.17 × 1.0 × 1.667 = 0.2833
- 费用率细分: 销售费用率=50/1000=0.05, 管理费用率=60/1000=0.06,
  研发费用率=30/1000=0.03, 财务费用率=22/1000=0.022
"""

from math import isclose

import pytest

from finance_agent.metrics.dupont import calc_dupont


class TestCalcDupont:
    def test_returns_l1_l2_l3(self, balance_sheet, income_statement):
        result = calc_dupont(balance_sheet, income_statement)
        assert "L1" in result
        assert "L2" in result
        assert "L3" in result

    def test_l1_roe_decomposition_2024(self, balance_sheet, income_statement):
        result = calc_dupont(balance_sheet, income_statement)
        l1 = result["L1"]["2024"]
        assert isclose(l1["净利率"], 0.17, rel_tol=1e-2)
        assert isclose(l1["总资产周转率"], 1.0, rel_tol=1e-2)
        assert isclose(l1["权益乘数"], 1000 / 600, rel_tol=1e-2)
        assert isclose(l1["ROE"], 0.17 * 1.0 * (1000 / 600), rel_tol=1e-2)

    def test_l2_profitability_drivers_2024(self, balance_sheet, income_statement):
        result = calc_dupont(balance_sheet, income_statement)
        l2 = result["L2"]["2024"]
        # 毛利率 = (1000-600)/1000 = 0.4
        assert isclose(l2["毛利率"], 0.4, rel_tol=1e-2)
        # 费用率 = (50+60+30+22)/1000 = 0.162
        assert isclose(l2["费用率"], 0.162, rel_tol=1e-2)

    def test_l3_expense_breakdown_2024(self, balance_sheet, income_statement):
        result = calc_dupont(balance_sheet, income_statement)
        l3 = result["L3"]["2024"]
        assert isclose(l3["销售费用率"], 50 / 1000, rel_tol=1e-2)
        assert isclose(l3["管理费用率"], 60 / 1000, rel_tol=1e-2)
        assert isclose(l3["研发费用率"], 30 / 1000, rel_tol=1e-2)
        assert isclose(l3["财务费用率"], 22 / 1000, rel_tol=1e-2)

    def test_roe_equals_three_factors(self, balance_sheet, income_statement):
        """验证 ROE = 净利率 × 周转率 × 权益乘数。"""
        result = calc_dupont(balance_sheet, income_statement)
        for year in ["2024", "2023", "2022"]:
            l1 = result["L1"][year]
            product = l1["净利率"] * l1["总资产周转率"] * l1["权益乘数"]
            assert isclose(l1["ROE"], product, rel_tol=1e-6), f"{year} ROE mismatch"

    def test_all_years_present(self, balance_sheet, income_statement):
        result = calc_dupont(balance_sheet, income_statement)
        for layer in ["L1", "L2", "L3"]:
            assert set(result[layer].keys()) == {"2024", "2023", "2022"}
