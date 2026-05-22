"""TDD tests for metrics/efficiency.py — 运营效率 4 指标。

指标：
1. 存货周转率（次）— AKShare 预计算
2. 应收账款周转率（次）— AKShare 预计算
3. 总资产周转率（次）— AKShare 预计算
4. 应付账款周转率（次）— 自算 = 营业成本 / 应付账款

注意：运营效率阈值使用行业均值倍数（ADR-0003），但计算本身不需要行业数据。

fixture 手算（2024）：
- 应付账款周转率 = 营业成本(600) / 应付账款(60) = 10
- 总资产周转率 = 营业收入(1000) / 资产总计(1000) = 1.0
"""

from math import isclose

import pytest

from finance_agent.metrics.efficiency import calc_efficiency


class TestCalcEfficiency:
    def test_returns_all_metrics(self, balance_sheet, income_statement, indicators):
        result = calc_efficiency(balance_sheet, income_statement, indicators)
        expected_keys = {"存货周转率", "应收账款周转率", "总资产周转率", "应付账款周转率"}
        assert set(result.keys()) == expected_keys

    def test_each_metric_has_all_years(self, balance_sheet, income_statement, indicators):
        result = calc_efficiency(balance_sheet, income_statement, indicators)
        for name, values in result.items():
            assert set(values.keys()) == {"2024", "2023", "2022"}, f"{name} years mismatch"

    def test_inventory_turnover_2024(self, balance_sheet, income_statement, indicators):
        result = calc_efficiency(balance_sheet, income_statement, indicators)
        # AKShare 预计算值
        assert isclose(result["存货周转率"]["2024"], 6.32, rel_tol=1e-2)

    def test_total_asset_turnover_2024(self, balance_sheet, income_statement, indicators):
        result = calc_efficiency(balance_sheet, income_statement, indicators)
        # 自算 = 营业收入/资产总计 = 1000/1000 = 1.0
        assert isclose(result["总资产周转率"]["2024"], 1.0, rel_tol=1e-2)

    def test_ap_turnover_2024(self, balance_sheet, income_statement, indicators):
        result = calc_efficiency(balance_sheet, income_statement, indicators)
        # 应付账款周转率 = 营业成本/应付账款 = 600/60 = 10
        assert isclose(result["应付账款周转率"]["2024"], 10.0, rel_tol=1e-2)

    def test_ap_turnover_2023(self, balance_sheet, income_statement, indicators):
        result = calc_efficiency(balance_sheet, income_statement, indicators)
        assert isclose(result["应付账款周转率"]["2023"], 550 / 50, rel_tol=1e-2)

    def test_zero_accounts_payable(self):
        import pandas as pd

        bs = pd.DataFrame(
            {"报告日": ["20241231"], "资产总计": [1000.0], "应付账款": [0.0]}
        )
        is_ = pd.DataFrame(
            {"报告日": ["20241231"], "营业收入": [1000.0], "营业成本": [600.0]}
        )
        ind = pd.DataFrame(
            {
                "日期": ["2024-12-31"],
                "存货周转率(次)": [6.0],
                "应收账款周转率(次)": [None],
                "总资产周转率(次)": [1.0],
            }
        )
        result = calc_efficiency(bs, is_, ind)
        assert result["应付账款周转率"]["2024"] is None
