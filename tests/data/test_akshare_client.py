"""TDD tests for data/akshare_client.py — AKShare 数据清洗逻辑。

测试重点：
- 年报过滤（只保留报告日以 1231 结尾的行）
- 列名提取和重映射
- 缺失值处理（NaN → None）
- 数据降级策略（必需数据缺失报错，非必需标记 N/A）
API 调用用 mock，不测外部网络。
"""

from unittest.mock import patch

import pandas as pd
import pytest

from finance_agent.data.akshare_client import AKShareClient


@pytest.fixture
def client():
    return AKShareClient()


class TestFilterAnnualReports:
    """年报过滤：只保留 1231 结尾的报告日。"""

    def test_keeps_annual_only(self, client):
        df = pd.DataFrame(
            {
                "报告日": ["20241231", "20240930", "20240630", "20240331", "20231231"],
                "value": [1, 2, 3, 4, 5],
            }
        )
        result = client._filter_annual(df)
        assert len(result) == 2
        assert list(result["报告日"]) == ["20241231", "20231231"]

    def test_empty_dataframe(self, client):
        df = pd.DataFrame({"报告日": [], "value": []})
        result = client._filter_annual(df)
        assert len(result) == 0

    def test_no_annual_reports(self, client):
        df = pd.DataFrame({"报告日": ["20240930", "20240630"], "value": [1, 2]})
        result = client._filter_annual(df)
        assert len(result) == 0


class TestNormalizeNaN:
    """NaN → None 转换。"""

    def test_nan_becomes_none(self, client):
        df = pd.DataFrame({"a": [1.0, float("nan"), 3.0], "b": ["x", None, "z"]})
        result = client._normalize_nan(df)
        assert pd.isna(result.iloc[1]["a"])
        assert result.iloc[0]["a"] == 1.0


class TestFetchBalanceSheet:
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_annual_only(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.return_value = pd.DataFrame(
            {
                "报告日": ["20241231", "20240930", "20231231"],
                "资产总计": [1000.0, 950.0, 900.0],
                "负债合计": [400.0, 380.0, 350.0],
            }
        )
        result = client.fetch_balance_sheet("600519")
        assert len(result) == 2
        assert "资产总计" in result.columns

    @patch("finance_agent.data.akshare_client.ak")
    def test_stocks_prefix_handling(self, mock_ak, client):
        """股票代码自动加 sh/sz 前缀。"""
        mock_ak.stock_financial_report_sina.return_value = pd.DataFrame(
            {"报告日": ["20241231", "20231231"], "资产总计": [100.0, 90.0]}
        )
        client.fetch_balance_sheet("600519")
        args = mock_ak.stock_financial_report_sina.call_args
        assert args[1]["stock"] == "sh600519" or args[0][0] == "sh600519"

    @patch("finance_agent.data.akshare_client.ak")
    def test_sz_prefix(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.return_value = pd.DataFrame(
            {"报告日": ["20241231", "20231231"], "资产总计": [100.0, 90.0]}
        )
        client.fetch_balance_sheet("000858")
        args = mock_ak.stock_financial_report_sina.call_args
        stock_arg = args[1].get("stock", args[0][0] if args[0] else "")
        assert "sz000858" in stock_arg


class TestFetchIncomeStatement:
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_annual_only(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.return_value = pd.DataFrame(
            {
                "报告日": ["20241231", "20240930", "20231231"],
                "营业收入": [1000.0, 750.0, 900.0],
                "净利润": [170.0, 130.0, 153.0],
            }
        )
        result = client.fetch_income_statement("600519")
        assert len(result) == 2
        assert result.iloc[0]["营业收入"] == 1000.0


class TestFetchCashFlow:
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_annual_only(self, mock_ak, client):
        mock_ak.stock_financial_report_sina.return_value = pd.DataFrame(
            {
                "报告日": ["20241231", "20240630", "20231231"],
                "经营活动产生的现金流量净额": [250.0, 120.0, 220.0],
            }
        )
        result = client.fetch_cash_flow("600519")
        assert len(result) == 2


class TestFetchIndicators:
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_dataframe(self, mock_ak, client):
        mock_ak.stock_financial_analysis_indicator.return_value = pd.DataFrame(
            {
                "日期": ["2024-12-31", "2023-12-31"],
                "销售毛利率(%)": [40.0, 38.0],
                "净资产收益率(%)": [28.0, 27.0],
            }
        )
        result = client.fetch_indicators("600519")
        assert len(result) == 2
        assert "销售毛利率(%)" in result.columns


class TestFetchIndustry:
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_industry_info(self, mock_ak, client):
        mock_ak.stock_individual_info_em.return_value = pd.DataFrame(
            {
                "item": ["行业", "总市值"],
                "value": ["白酒", "2000000000000"],
            }
        )
        result = client.fetch_industry("600519")
        assert result["行业"] == "白酒"


class TestFetchStockQuote:
    @patch("finance_agent.data.akshare_client.ak")
    def test_returns_quote(self, mock_ak, client):
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame(
            {
                "代码": ["600519", "000858"],
                "名称": ["贵州茅台", "五粮液"],
                "最新价": [1800.0, 150.0],
                "市盈率-动态": [25.0, 20.0],
                "市净率": [10.0, 5.0],
            }
        )
        result = client.fetch_stock_quote("600519")
        assert result["最新价"] == 1800.0
        assert result["市盈率-动态"] == 25.0


class TestMinYearCheck:
    def test_less_than_2_years_raises(self, client):
        """不足 2 年报错。"""
        df = pd.DataFrame({"报告日": ["20241231"], "value": [1]})
        with pytest.raises(ValueError):  # "不足 2 年"
            client._check_min_years(df, "600519")

    def test_exactly_2_years_ok(self, client):
        df = pd.DataFrame({"报告日": ["20241231", "20231231"], "value": [1, 2]})
        client._check_min_years(df, "600519")  # should not raise
