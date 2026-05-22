"""TDD tests for metrics/solvency.py — 偿债 5 指标。

指标：
1. 资产负债率（AKShare 预计算）
2. 流动比率（AKShare 预计算）
3. 速动比率（AKShare 预计算）
4. 利息覆盖倍数（自算：EBIT / 利息费用）
5. 净债务/EBITDA（自算）

fixture 数据手算验证：
- 2024: 资产总计=1000, 负债合计=400, 流动资产=500, 流动负债=300, 存货=100
  - 资产负债率 = 400/1000 = 40%
  - 流动比率 = 500/300 = 1.667
  - 速动比率 = (500-100)/300 = 1.333
  - 利息覆盖倍数 = (200+20)/20 = 11
  - 净债务 = 有息负债(80+50+30+20) - 现金(200) = -20
  - EBITDA = 利润总额(200) + 利息费用(20) + 折旧变动(120-100=20) = 240
  - 净债务/EBITDA = -20/240 = -0.083
"""

from math import isclose

import pandas as pd
import pytest

from finance_agent.metrics.solvency import calc_solvency


class TestCalcSolvency:
    """偿债指标计算测试。"""

    def test_returns_dict_with_all_metrics(self, balance_sheet, income_statement, indicators):
        result = calc_solvency(balance_sheet, income_statement, indicators)
        expected_keys = {
            "资产负债率",
            "流动比率",
            "速动比率",
            "利息覆盖倍数",
            "净债务/EBITDA",
        }
        assert set(result.keys()) == expected_keys

    def test_each_metric_has_all_years(self, balance_sheet, income_statement, indicators):
        result = calc_solvency(balance_sheet, income_statement, indicators)
        for metric_name, values in result.items():
            assert isinstance(values, dict), f"{metric_name} should be dict"
            assert set(values.keys()) == {"2024", "2023", "2022"}, (
                f"{metric_name} years mismatch"
            )

    # ── 2024 验证 ──

    def test_debt_asset_ratio_2024(self, balance_sheet, income_statement, indicators):
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["资产负债率"]["2024"], 40.0, rel_tol=1e-3)

    def test_current_ratio_2024(self, balance_sheet, income_statement, indicators):
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["流动比率"]["2024"], 500 / 300, rel_tol=1e-3)

    def test_quick_ratio_2024(self, balance_sheet, income_statement, indicators):
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["速动比率"]["2024"], (500 - 100) / 300, rel_tol=1e-3)

    def test_interest_coverage_2024(self, balance_sheet, income_statement, indicators):
        # EBIT = 利润总额 + 利息费用 = 200 + 20 = 220
        # 利息覆盖倍数 = 220 / 20 = 11
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["利息覆盖倍数"]["2024"], 11.0, rel_tol=1e-3)

    def test_net_debt_to_ebitda_2024(self, balance_sheet, income_statement, indicators):
        # 有息负债 = 短期借款(80) + 长期借款(50) + 应付债券(30) + 一年内到期(20) = 180
        # 净债务 = 180 - 货币资金(200) = -20
        # EBITDA = 利润总额(200) + 利息费用(20) + 折旧变动(120-100=20) = 240
        # 净债务/EBITDA = -20/240 ≈ -0.0833
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["净债务/EBITDA"]["2024"], -20 / 240, rel_tol=1e-2)

    # ── 2023 跨年验证 ──

    def test_debt_asset_ratio_2023(self, balance_sheet, income_statement, indicators):
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["资产负债率"]["2023"], 350 / 900 * 100, rel_tol=1e-3)

    def test_interest_coverage_2023(self, balance_sheet, income_statement, indicators):
        # EBIT = 180 + 18 = 198, 利息费用 = 18 → 198/18 = 11
        result = calc_solvency(balance_sheet, income_statement, indicators)
        assert isclose(result["利息覆盖倍数"]["2023"], 11.0, rel_tol=1e-3)

    # ── 边界：利息费用为零 ──

    def test_zero_interest_expense(self, balance_sheet, income_statement, indicators):
        is_mod = income_statement.copy()
        is_mod["利息费用"] = [0.0, 0.0, 0.0]
        is_mod["财务费用"] = [0.0, 0.0, 0.0]
        result = calc_solvency(balance_sheet, is_mod, indicators)
        # 利息费用为零时利息覆盖倍数应为 inf 或 None
        for year in ["2024", "2023", "2022"]:
            val = result["利息覆盖倍数"][year]
            assert val is None or val == float("inf"), (
                f"利息覆盖倍数在利息费用为零时应为 None 或 inf, got {val}"
            )

    # ── 边界：EBITDA 为零 ──

    def test_zero_ebitda(self):
        bs = pd.DataFrame(
            {
                "报告日": ["20241231"],
                "货币资金": [100.0],
                "存货": [0.0],
                "流动资产合计": [200.0],
                "固定资产净值": [100.0],
                "累计折旧": [0.0],
                "非流动资产合计": [200.0],
                "资产总计": [400.0],
                "短期借款": [50.0],
                "应付账款": [0.0],
                "一年内到期的非流动负债": [0.0],
                "流动负债合计": [100.0],
                "长期借款": [0.0],
                "应付债券": [0.0],
                "非流动负债合计": [50.0],
                "负债合计": [150.0],
                "所有者权益(或股东权益)合计": [250.0],
                "实收资本(或股本)": [100.0],
                "未分配利润": [50.0],
            }
        )
        is_ = pd.DataFrame(
            {
                "报告日": ["20241231"],
                "营业收入": [0.0],
                "营业成本": [0.0],
                "销售费用": [0.0],
                "管理费用": [0.0],
                "研发费用": [0.0],
                "财务费用": [0.0],
                "利息费用": [0.0],
                "营业利润": [0.0],
                "利润总额": [0.0],
                "所得税费用": [0.0],
                "净利润": [0.0],
                "归属于母公司所有者的净利润": [0.0],
            }
        )
        ind = pd.DataFrame(
            {
                "日期": ["2024-12-31"],
                "销售毛利率(%)": [0.0],
                "销售净利率(%)": [0.0],
                "净资产收益率(%)": [0.0],
                "总资产净利润率(%)": [0.0],
                "存货周转率(次)": [0.0],
                "应收账款周转率(次)": [None],
                "总资产周转率(次)": [0.0],
                "流动比率": [2.0],
                "速动比率": [2.0],
                "资产负债率(%)": [37.5],
                "利息支付倍数": [None],
            }
        )
        result = calc_solvency(bs, is_, ind)
        val = result["净债务/EBITDA"]["2024"]
        assert val is None, f"EBITDA 为零时净债务/EBITDA 应为 None, got {val}"
