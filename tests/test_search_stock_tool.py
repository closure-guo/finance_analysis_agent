"""search_stock 工具测试。

验证 search_stock 工具正确包装 search_stock_tool 并返回格式化结果。
"""

from unittest.mock import patch

import pytest

from finance_agent.agent_factory import _make_search_stock


class TestSearchStockTool:
    """search_stock 工具行为测试。"""

    @pytest.mark.asyncio
    async def test_resolves_stock_name_to_code(self):
        """工具将"茅台"解析为股票代码 600519。"""
        mock_result = {
            "candidates": [{"code": "600519", "name": "贵州茅台", "market": "SH"}],
            "found": True,
            "source": "akshare_exact",
            "confidence": 1.0,
        }

        with patch("finance_agent.react_agent.search_stock_tool", return_value=mock_result):
            search_stock = _make_search_stock(api_key="test-key")
            result = await search_stock(query="茅台")

        assert "600519" in result
        assert "贵州茅台" in result

    @pytest.mark.asyncio
    async def test_not_found_returns_message(self):
        """未找到股票时返回提示信息。"""
        mock_result = {
            "candidates": [],
            "found": False,
            "message": "未找到匹配的股票",
        }

        with patch("finance_agent.react_agent.search_stock_tool", return_value=mock_result):
            search_stock = _make_search_stock(api_key="test-key")
            result = await search_stock(query="不存在的股票")

        assert "未找到" in result or "未找到匹配" in result

    @pytest.mark.asyncio
    async def test_multiple_candidates(self):
        """多候选时返回所有选项。"""
        mock_result = {
            "candidates": [
                {"code": "600519", "name": "贵州茅台", "market": "SH"},
                {"code": "000858", "name": "五粮液", "market": "SZ"},
            ],
            "found": True,
            "source": "akshare_fuzzy",
            "confidence": 0.4,
            "needs_confirmation": True,
        }

        with patch("finance_agent.react_agent.search_stock_tool", return_value=mock_result):
            search_stock = _make_search_stock(api_key="test-key")
            result = await search_stock(query="茅台")

        assert "600519" in result
        assert "贵州茅台" in result
        assert "000858" in result
        assert "五粮液" in result

    @pytest.mark.asyncio
    async def test_api_key_passed_through(self):
        """api_key 通过闭包正确传递给 search_stock_tool。"""
        with patch("finance_agent.react_agent.search_stock_tool") as mock_func:
            mock_func.return_value = {"candidates": [], "found": False, "message": "test"}
            search_stock = _make_search_stock(api_key="my-secret-key")
            await search_stock(query="茅台")

            mock_func.assert_called_once_with("茅台", "my-secret-key")
