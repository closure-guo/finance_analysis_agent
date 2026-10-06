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
from pathlib import Path

import pandas as pd
import pytest

from finance_agent.data.akshare_client import AKShareClient
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

    def test_roe_prefers_weighted_from_indicators(self):
        """indicators 有加权净资产收益率时，ROE 应优先使用，而非自算期末权益。

        模拟 300308 场景：期末权益 ROE=36.27%，加权 ROE=44.16%。
        """
        import pandas as pd

        bs = pd.DataFrame(
            {
                "报告日": ["20241231", "20231231"],
                "资产总计": [1000.0, 900.0],
                "所有者权益(或股东权益)合计": [600.0, 550.0],
                "归母所有者权益": [580.0, 530.0],
                "短期借款": [80.0, 70.0],
                "长期借款": [50.0, 40.0],
                "应付债券": [30.0, 20.0],
                "一年内到期的非流动负债": [20.0, 15.0],
            }
        )
        is_ = pd.DataFrame(
            {
                "报告日": ["20241231", "20231231"],
                "营业收入": [1000.0, 900.0],
                "营业成本": [600.0, 550.0],
                "净利润": [170.0, 153.0],
                "归母净利润": [168.0, 151.0],
                "利润总额": [200.0, 180.0],
                "所得税费用": [30.0, 27.0],
                "利息费用": [20.0, 18.0],
            }
        )
        # 加权 ROE=44.16%，与期末权益 ROE=168/580=28.97% 差异大
        ind = pd.DataFrame(
            {
                "日期": ["2024-12-31", "2023-12-31"],
                "加权净资产收益率(%)": [44.16, 31.23],
            }
        )

        result = calc_profitability(bs, is_, ind)

        # ROE 应取加权值 44.16，不是期末权益自算值 28.97
        assert isclose(result["ROE"]["2024"], 44.16, rel_tol=1e-2)
        assert isclose(result["ROE"]["2023"], 31.23, rel_tol=1e-2)

    def test_roe_fallback_avg_equity_when_no_indicators(self):
        """indicators 无该年数据时，用归母净利润/平均归母权益自算。

        2025: 归母净利润=200, 归母权益(2025)=700, 归母权益(2024)=580
        平均权益 = (700+580)/2 = 640
        ROE = 200/640*100 = 31.25%
        """
        import pandas as pd

        bs = pd.DataFrame(
            {
                "报告日": ["20251231", "20241231"],
                "资产总计": [1100.0, 1000.0],
                "所有者权益(或股东权益)合计": [700.0, 600.0],
                "归母所有者权益": [700.0, 580.0],
                "短期借款": [80.0, 70.0],
                "长期借款": [50.0, 40.0],
                "应付债券": [30.0, 20.0],
                "一年内到期的非流动负债": [20.0, 15.0],
            }
        )
        is_ = pd.DataFrame(
            {
                "报告日": ["20251231", "20241231"],
                "营业收入": [1200.0, 1000.0],
                "营业成本": [700.0, 600.0],
                "净利润": [210.0, 170.0],
                "归母净利润": [200.0, 168.0],
                "利润总额": [240.0, 200.0],
                "所得税费用": [36.0, 30.0],
                "利息费用": [20.0, 18.0],
            }
        )
        # indicators 只有 2024，无 2025
        ind = pd.DataFrame(
            {
                "日期": ["2024-12-31"],
                "加权净资产收益率(%)": [44.16],
            }
        )

        result = calc_profitability(bs, is_, ind)

        # 2025: 无 indicators → 自算 200/((700+580)/2)*100 = 31.25%
        assert isclose(result["ROE"]["2025"], 200 / 640 * 100, rel_tol=1e-2)
        # 2024: 有 indicators → 用加权值 44.16
        assert isclose(result["ROE"]["2024"], 44.16, rel_tol=1e-2)


class TestMissingInputSemantics:
    """add-chart-data-integrity R2：派生比率缺失输入不产出伪值。

    背景同 tests/data/test_parent_col_resolution.py——银行模板列解析
    修复后，银行报表（无营业成本列、归母权益为真实列）走本模块时：
    毛利率必须为 None 而非 100% 伪值；ROE 回退分母必须是真实归母权益。
    """

    @pytest.fixture
    def bank_frames(self):
        """返回 (改名后 income, 改名后 balance, 原始 income, 原始 balance)。

        期望值从原始 frame 的真实归母列自算，保证断言值与被测值不同源。
        """
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        raw_income = pd.read_csv(fixtures / "sina_income_601818_bank.csv")
        raw_balance = pd.read_csv(fixtures / "sina_balance_601818_bank.csv")
        client = AKShareClient()
        income = client._rename_parent_cols(raw_income.copy())
        balance = client._rename_parent_cols(raw_balance.copy())
        return income, balance, raw_income, raw_balance

    def test_bank_report_gross_margin_all_none(self, bank_frames):
        """银行利润表无营业成本列 → 毛利率各年 None，MUST NOT 出现 100.0。"""
        income, balance, _raw_income, _raw_balance = bank_frames
        result = calc_profitability(balance, income, None)
        assert all(v is None for v in result["毛利率"].values())
        assert 100.0 not in {v for v in result["毛利率"].values() if v is not None}

    def test_bank_report_roe_uses_real_parent_equity(self, bank_frames):
        """ROE 回退分母 = 真实归母权益（非「未分配利润」错列）。

        期望值直接从 fixture 原始列自算（自洽，不硬编码财务数字）：
        最旧年（序列末位）无上年权益 → 用当年归母权益。
        """
        income, balance, raw_income, raw_balance = bank_frames
        result = calc_profitability(balance, income, None)
        oldest = -1
        ni = float(raw_income.iloc[oldest]["归属于母公司的净利润"])
        equity = float(raw_balance.iloc[oldest]["归属于母公司股东的权益"])
        expected = ni / equity * 100
        year = str(income.iloc[oldest]["报告日"])[:4]
        assert isclose(result["ROE"][year], expected, rel_tol=1e-6)
        # 合理性护栏：银行 ROE 在个位数量级，MUST NOT 复现 28% 伪值
        assert result["ROE"][year] < 20.0

    def test_zero_cost_with_positive_revenue_is_missing_margin(self):
        """营业成本为 0 而收入 > 0：视为缺失，毛利率 None。"""
        bs = pd.DataFrame(
            {
                "报告日": ["20241231", "20231231"],
                "资产总计": [1000.0, 900.0],
                "所有者权益(或股东权益)合计": [600.0, 550.0],
                "短期借款": [0.0] * 2,
                "长期借款": [0.0] * 2,
                "应付债券": [0.0] * 2,
                "一年内到期的非流动负债": [0.0] * 2,
            }
        )
        is_ = pd.DataFrame(
            {
                "报告日": ["20241231", "20231231"],
                "营业收入": [1000.0, 900.0],
                "营业成本": [0.0, 0.0],
                "净利润": [170.0, 153.0],
                "利润总额": [200.0, 180.0],
                "所得税费用": [30.0, 27.0],
                "利息费用": [0.0, 0.0],
            }
        )
        result = calc_profitability(bs, is_, None)
        assert result["毛利率"]["2024"] is None
        assert result["毛利率"]["2023"] is None

    def test_roe_none_when_equity_input_missing(self):
        """归母权益与所有者权益合计均缺失 → ROE 回退输出 None，不产出伪值。"""
        bs = pd.DataFrame(
            {
                "报告日": ["20241231", "20231231"],
                "资产总计": [1000.0, 900.0],
                "短期借款": [0.0] * 2,
                "长期借款": [0.0] * 2,
                "应付债券": [0.0] * 2,
                "一年内到期的非流动负债": [0.0] * 2,
            }
        )
        is_ = pd.DataFrame(
            {
                "报告日": ["20241231", "20231231"],
                "营业收入": [1000.0, 900.0],
                "营业成本": [600.0, 550.0],
                "归母净利润": [168.0, 151.0],
                "利润总额": [200.0, 180.0],
                "所得税费用": [30.0, 27.0],
                "利息费用": [0.0, 0.0],
            }
        )
        result = calc_profitability(bs, is_, None)
        assert result["ROE"]["2024"] is None
        assert result["ROE"]["2023"] is None
