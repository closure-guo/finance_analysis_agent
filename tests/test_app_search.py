"""app_search.py 单元测试 — 验证搜索功能。"""

import logging
from unittest.mock import patch

import pandas as pd
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


def _full_stock_df() -> pd.DataFrame:
    """构造超过 _MIN_VALID_LIST_SIZE 的完整列表 DataFrame（模拟真实全 A 股抓取结果）。"""
    return pd.DataFrame(
        {
            "code": [f"{600000 + i:06d}" for i in range(1200)],
            "name": [f"股票{i}" for i in range(1200)],
        }
    )


class TestGetStockListResilience:
    """get_stock_list 抓取失败韧性。

    根因背景（incident 032）：抓取异常时空列表被永久写入缓存，进程内所有
    股票检索（含四级降级的验证锚点）全量失效，直到重启。契约：
    失败/异常小的结果不缓存，短冷却内不重复打上游，冷却过后自动重试。
    """

    @pytest.fixture(autouse=True)
    def _reset_cache_state(self):
        import finance_agent.app_search as app_search

        app_search._STOCK_LIST_CACHE = None
        app_search._STOCK_LIST_FAILURE_TS = 0.0
        yield
        app_search._STOCK_LIST_CACHE = None
        app_search._STOCK_LIST_FAILURE_TS = 0.0

    def test_fetch_failure_not_cached_and_recovers_on_retry(self):
        import finance_agent.app_search as app_search

        with patch.object(
            app_search.ak,
            "stock_info_a_code_name",
            side_effect=[RuntimeError("网络抖动"), _full_stock_df()],
        ):
            first = app_search.get_stock_list()
            assert first == []

            app_search._STOCK_LIST_FAILURE_TS = 0.0  # 模拟冷却过期
            second = app_search.get_stock_list()
            assert len(second) == 1200
            assert second[0] == {"code": "600000", "name": "股票0"}

    def test_suspiciously_small_list_rejected_and_refetched(self):
        import finance_agent.app_search as app_search

        tiny_df = pd.DataFrame({"code": ["600519"], "name": ["贵州茅台"]})
        with patch.object(
            app_search.ak,
            "stock_info_a_code_name",
            side_effect=[tiny_df, _full_stock_df()],
        ):
            first = app_search.get_stock_list()
            assert first == []

            app_search._STOCK_LIST_FAILURE_TS = 0.0  # 模拟冷却过期
            second = app_search.get_stock_list()
            assert len(second) == 1200

    def test_failure_cooldown_skips_upstream_then_recovers(self):
        import finance_agent.app_search as app_search

        call_count = {"n": 0}

        def _fail():
            call_count["n"] += 1
            raise RuntimeError("上游不可用")

        with patch.object(app_search.ak, "stock_info_a_code_name", side_effect=_fail):
            assert app_search.get_stock_list() == []
            assert app_search.get_stock_list() == []
        assert call_count["n"] == 1  # 冷却期内不打上游

        app_search._STOCK_LIST_FAILURE_TS = 0.0  # 模拟冷却过期
        with patch.object(app_search.ak, "stock_info_a_code_name", return_value=_full_stock_df()):
            assert len(app_search.get_stock_list()) == 1200

    def test_fetch_failure_logs_warning(self, caplog):
        import finance_agent.app_search as app_search

        with (
            patch.object(
                app_search.ak,
                "stock_info_a_code_name",
                side_effect=RuntimeError("网络抖动"),
            ),
            caplog.at_level(logging.WARNING, logger="finance_agent.app_search"),
        ):
            assert app_search.get_stock_list() == []

        assert any("抓取失败" in r.message for r in caplog.records)
