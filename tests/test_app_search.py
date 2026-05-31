"""app_search.py 单元测试 — 验证搜索功能。"""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_stock_list():
    return [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000858", "name": "五粮液"},
        {"code": "000568", "name": "泸州老窖"},
        {"code": "000001", "name": "平安银行"},
    ]


@patch("finance_agent.app_search.get_stock_list")
def test_search_by_code(mock_get_list, mock_stock_list):
    mock_get_list.return_value = mock_stock_list

    from finance_agent.app_search import search_stocks

    results = search_stocks("600519")
    assert len(results) == 1
    assert results[0][1] == "600519"


@patch("finance_agent.app_search.get_stock_list")
def test_search_by_name(mock_get_list, mock_stock_list):
    mock_get_list.return_value = mock_stock_list

    from finance_agent.app_search import search_stocks

    results = search_stocks("茅台")
    assert len(results) == 1
    assert results[0][1] == "600519"


@patch("finance_agent.app_search.get_stock_list")
def test_search_empty_query(mock_get_list, mock_stock_list):
    mock_get_list.return_value = mock_stock_list

    from finance_agent.app_search import search_stocks

    results = search_stocks("")
    assert results == []


@patch("finance_agent.app_search.get_stock_list")
def test_search_limit(mock_get_list, mock_stock_list):
    mock_get_list.return_value = mock_stock_list

    from finance_agent.app_search import search_stocks

    results = search_stocks("0", limit=2)
    assert len(results) == 2
