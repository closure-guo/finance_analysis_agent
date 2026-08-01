"""网络搜索 Langfuse span 测试。

验证 tavily_search 执行时创建 search_api_call span。
"""

from unittest.mock import MagicMock, patch

from finance_agent.web_search import tavily_search


class TestSearchApiCallSpan:
    """网络搜索 span 可观测测试。"""

    def test_search_creates_search_api_call_span(self, monkeypatch):
        """搜索执行时创建 search_api_call span，记录 input 与 output。"""
        # tavily_search 直接读 os.environ.get("TAVILY_API_KEY")，
        # 单独 patch has_tavily_key 不够，必须确保环境变量存在
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        mockTavily = MagicMock()
        mockTavily.search.return_value = {
            "results": [{"title": "测试结果", "url": "https://example.com", "content": "内容"}],
            "answer": "AI 摘要",
        }

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=mockTavily),
            patch("finance_agent.web_search.open_span") as mockOpenSpan,
        ):
            mockObs = MagicMock()
            mockOpenSpan.return_value.__enter__.return_value = mockObs
            response = tavily_search("测试查询", max_results=3)

        # 验证 open_span 被调用创建 search_api_call span
        mockOpenSpan.assert_called_once_with(
            name="search_api_call",
            input={"query": "测试查询", "max_results": 3},
        )
        # 验证 output 记录了结果数量
        mockObs.update.assert_called_once_with(output={"count": 1})
        # 验证搜索结果正确
        assert response.count == 1
        assert response.results[0].title == "测试结果"

    def test_search_span_degrades_when_langfuse_unconfigured(self, monkeypatch):
        """Langfuse 未配置时 span 降级，搜索仍正常返回结果。"""
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        mockTavily = MagicMock()
        mockTavily.search.return_value = {
            "results": [{"title": "t", "url": "http://x", "content": "c"}],
            "answer": None,
        }

        with (
            patch("finance_agent.web_search.has_tavily_key", return_value=True),
            patch("tavily.TavilyClient", return_value=mockTavily),
            patch("finance_agent.web_search.open_span") as mockOpenSpan,
        ):
            # 模拟 open_span 真实降级行为：yield None
            from contextlib import contextmanager

            @contextmanager
            def _real_open_span(name, input=None):
                yield None

            mockOpenSpan.side_effect = _real_open_span
            response = tavily_search("降级测试", max_results=5)

        # 即使 span 降级，搜索结果仍正确
        assert response.count == 1
        assert response.query == "降级测试"
