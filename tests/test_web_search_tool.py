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


class TestDetectSearchTopic:
    """新闻意图词表判别（add-news-topic-search，TDD 先行）。"""

    def test_news_intent_keywords_hit(self):
        from finance_agent.web_search import detect_search_topic

        for q in ("贵州茅台 最新消息", "央行 近期 货币政策动态", "今天 A股 大跌新闻", "本周 央行动向"):
            assert detect_search_topic(q) == "news", q

    def test_non_news_query_stays_general(self):
        from finance_agent.web_search import detect_search_topic

        for q in ("贵州茅台 股价", "A股 2026年 降准 货币政策", "600519 市盈率"):
            assert detect_search_topic(q) is None, q

    def test_year_alone_is_not_news_intent(self):
        """react_agent 会在 query 尾部拼年份（如「... 2026」），年份本身不构成新闻意图。"""
        from finance_agent.web_search import detect_search_topic

        assert detect_search_topic("贵州茅台 财务分析 2026") is None


class TestTavilySearchTopicPassthrough:
    """tavily_search 按 topic 透传 TavilyClient（mock 层验证）。"""

    def _mock_client(self):
        from unittest.mock import MagicMock

        client = MagicMock()
        client.search.return_value = {"results": [], "answer": None}
        return client

    def test_news_intent_query_uses_news_topic(self):
        from unittest.mock import patch

        from finance_agent import web_search

        client = self._mock_client()
        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=client),
        ):
            web_search.tavily_search("贵州茅台 最新消息")
        assert client.search.call_args.kwargs.get("topic") == "news"

    def test_general_query_passes_no_topic(self):
        from unittest.mock import patch

        from finance_agent import web_search

        client = self._mock_client()
        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=client),
        ):
            web_search.tavily_search("贵州茅台 股价")
        # general 走现状：不传 topic（Tavily 默认 general）
        assert client.search.call_args.kwargs.get("topic") is None

    def test_explicit_topic_overrides_detection(self):
        from unittest.mock import patch

        from finance_agent import web_search

        client = self._mock_client()
        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=client),
        ):
            web_search.tavily_search("贵州茅台 最新消息", topic="general")
        assert client.search.call_args.kwargs.get("topic") == "general"


class TestMultiAngleGuidance:
    """多角度检索引导契约（add-news-topic-search 扩展，TDD 先行）。

    实测（2026-09-12，3 场景）：多角度 query 有效信息 ~3 倍（6.5→25 条中有效数），
    但角度选择 > 数量（行情类 query 5 条全为行情页 0 有效）。引导写入工具描述。
    """

    def test_batch_web_search_description_guides_2_3_angles(self):
        from finance_agent.agent_factory import _make_batch_web_search

        tool = _make_batch_web_search([])
        doc = tool.__doc__ or ""
        assert "2-3 个不同角度" in doc
        assert "行情" in doc  # 行情报价类召回多为行情页，不作搜索角度

    def test_web_search_description_redirects_news_to_batch(self):
        from finance_agent.agent_factory import _make_web_search_with_collector

        tool = _make_web_search_with_collector([])
        doc = tool.__doc__ or ""
        assert "batch_web_search" in doc  # 新闻/舆情多角度引导
        assert "行情" in doc
