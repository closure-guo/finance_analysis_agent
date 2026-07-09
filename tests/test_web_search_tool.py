"""web_search 工具测试。

验证 web_search 工具正确包装 Tavily API 并返回格式化结果。
"""

from unittest.mock import patch

import pytest

from finance_agent.agent_factory import _web_search
from finance_agent.web_search import SearchResponse, SearchResult


class TestWebSearchTool:
    """web_search 工具行为测试。"""

    @pytest.mark.asyncio
    async def test_returns_formatted_results(self):
        """工具返回格式化的搜索结果字符串。"""
        mock_response = SearchResponse(
            query="茅台 股价",
            results=[
                SearchResult(
                    title="贵州茅台股价",
                    url="https://finance.example.com/600519",
                    content="贵州茅台今日股价 1800 元",
                ),
                SearchResult(
                    title="茅台最新消息",
                    url="https://news.example.com/maotai",
                    content="茅台发布季度财报",
                ),
            ],
            count=2,
        )

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("finance_agent.web_search.tavily_search", return_value=mock_response),
        ):
            result = await _web_search("茅台 股价")

        assert "[1]" in result
        assert "贵州茅台股价" in result
        assert "https://finance.example.com/600519" in result
        assert "贵州茅台今日股价 1800 元" in result
        assert "[2]" in result
        assert "茅台最新消息" in result

    @pytest.mark.asyncio
    async def test_returns_error_without_api_key(self):
        """未配置 TAVILY_API_KEY 时返回错误信息。"""
        with patch("finance_agent.web_search.has_tavily_key", return_value=False):
            result = await _web_search("anything")

        assert "错误" in result or "TAVILY_API_KEY" in result

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """搜索无结果时返回空字符串。"""
        mock_response = SearchResponse(
            query="不存在的关键词",
            results=[],
            count=0,
        )

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("finance_agent.web_search.tavily_search", return_value=mock_response),
        ):
            result = await _web_search("不存在的关键词")

        assert result == "" or result.strip() == ""
