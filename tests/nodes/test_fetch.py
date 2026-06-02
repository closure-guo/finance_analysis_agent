"""TDD tests for nodes/fetch.py — fetch_data 节点。

fetch_data 职责：
1. Step1 并行拉取无依赖数据（三大报表 + 行情 + 行业归属 + 预计算指标）
2. Step2 拉取同业数据（依赖 Step1 的行业归属）
3. 拉取后写入缓存
4. 数据降级：三大报表缺失 → 报错终止；同业缺失 → 标记 N/A 继续
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from finance_agent.nodes.fetch import fetch_data


def _make_balance_sheet():
    return pd.DataFrame({"报告日": ["20241231", "20231231"], "资产总计": [1000.0, 900.0]})


def _make_income():
    return pd.DataFrame({"报告日": ["20241231", "20231231"], "营业收入": [1000.0, 900.0]})


def _make_cashflow():
    return pd.DataFrame(
        {"报告日": ["20241231", "20231231"], "经营活动产生的现金流量净额": [250.0, 220.0]}
    )


def _make_indicators():
    return pd.DataFrame({"日期": ["2024-12-31", "2023-12-31"], "销售毛利率(%)": [40.0, 38.0]})


def _setup_client():
    mock = MagicMock()
    mock.fetch_balance_sheet.return_value = _make_balance_sheet()
    mock.fetch_income_statement.return_value = _make_income()
    mock.fetch_cash_flow.return_value = _make_cashflow()
    mock.fetch_indicators.return_value = _make_indicators()
    mock.fetch_industry.return_value = {"industry": "白酒", "name": "贵州茅台"}
    mock.fetch_stock_quote.return_value = {"price": 1800.0, "name": "贵州茅台", "code": "600519"}
    return mock


class TestFetchDataBasic:
    def test_fills_all_state_fields(self):
        mock_client = _setup_client()
        mock_cache = MagicMock()
        state = {"stock_code": "600519"}
        result = fetch_data(state, cache=mock_cache, client=mock_client)

        assert result["balance_sheet"] is not None
        assert result["income_statement"] is not None
        assert result["cash_flow_statement"] is not None
        assert result["financial_indicators"] is not None
        assert result["industry_info"]["industry"] == "白酒"
        assert result["stock_quote"]["price"] == 1800.0

    def test_writes_to_cache(self):
        mock_client = _setup_client()
        mock_cache = MagicMock()
        state = {"stock_code": "600519"}
        fetch_data(state, cache=mock_cache, client=mock_client)

        assert mock_cache.set.call_count >= 3
        cached_keys = [call[0][0] for call in mock_cache.set.call_args_list]
        assert "600519:balance_sheet" in cached_keys
        assert "600519:income_statement" in cached_keys
        assert "600519:cash_flow_statement" in cached_keys


class TestFetchDataDegradation:
    def test_required_data_missing_raises(self):
        """三大报表拉取失败应报错终止。"""
        mock_client = MagicMock()
        mock_client.fetch_balance_sheet.side_effect = Exception("API error")
        mock_cache = MagicMock()
        state = {"stock_code": "600519"}
        with pytest.raises(Exception, match="API error"):
            fetch_data(state, cache=mock_cache, client=mock_client)

    def test_peer_data_missing_marks_na(self):
        """同业数据拉取失败时标记 N/A 继续。"""
        mock_client = _setup_client()
        mock_client.fetch_peer_data.side_effect = Exception("no peers")
        mock_cache = MagicMock()
        state = {"stock_code": "600519", "peer_codes": ["000858"]}
        result = fetch_data(state, cache=mock_cache, client=mock_client)
        assert result.get("peer_financials") is None
