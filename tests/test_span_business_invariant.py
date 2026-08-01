"""span 业务行为不变回归测试。

验证 span 创建不改变 SSE 事件流、工具执行结果、搜索结果。
"""

from unittest.mock import MagicMock, patch

import pytest

from finance_agent.harness import Agent, PermissionMode
from finance_agent.harness.llm_client import LLMResponse
from finance_agent.web_search import tavily_search


class MockLLMClient:
    """模拟 LLM 客户端。"""

    def __init__(self, responses):
        self._responses = responses
        self._callIndex = 0

    async def chat_stream(self, messages=None, tools=None, temperature=0.7, tool_choice=None):
        if self._callIndex >= len(self._responses):
            yield LLMResponse(text_delta="", is_finished=True)
            return
        chunks = self._responses[self._callIndex]
        self._callIndex += 1
        for chunk in chunks:
            yield chunk


def _make_tool_call(name, arguments):
    from finance_agent.harness.types import ToolCallRequest

    return ToolCallRequest(id="call_test", name=name, arguments=arguments)


@pytest.fixture
def echo_tool():
    async def echo(text: str) -> str:
        """回显

        Args:
            text: 文本
        """
        return f"echo: {text}"

    return echo


class TestSpanBusinessInvariant:
    """span 不改变业务行为测试。"""

    @pytest.mark.asyncio
    async def test_span_transparent_to_sse_events(self, echo_tool):
        """有 span 时 SSE 事件流与无 span 时完全一致。"""
        mockLlm = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="查",
                        tool_calls=[_make_tool_call("echo", {"text": "hi"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="done", is_finished=True)],
            ]
        )
        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mockLlm,
        )
        agent.tools.register(echo_tool, name="echo")

        # 收集事件流（open_span 真实降级为 None，模拟无 span）
        from contextlib import contextmanager

        @contextmanager
        def _noop_span(name, input=None):
            yield None

        eventsNoSpan = []
        with patch("finance_agent.harness.loop.open_span", side_effect=_noop_span):
            async for event in agent.run("测试"):
                eventsNoSpan.append((event.event_type, event.content))

        # 重新运行（open_span 真实创建 mock span）
        mockLlm2 = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="查",
                        tool_calls=[_make_tool_call("echo", {"text": "hi"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="done", is_finished=True)],
            ]
        )
        agent2 = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mockLlm2,
        )
        agent2.tools.register(echo_tool, name="echo")
        mockObs = MagicMock()
        eventsWithSpan = []
        with patch("finance_agent.harness.loop.open_span") as mockOpenSpan:
            mockOpenSpan.return_value.__enter__.return_value = mockObs
            async for event in agent2.run("测试"):
                eventsWithSpan.append((event.event_type, event.content))

        # 事件流完全一致（span 不改变业务输出）
        assert eventsNoSpan == eventsWithSpan

    def test_search_result_invariant_with_span_exception(self, monkeypatch):
        """span 创建抛异常时，搜索结果仍正确返回。"""
        # tavily_search 直接读 os.environ.get("TAVILY_API_KEY")，
        # 单独 patch has_tavily_key 不够，必须确保环境变量存在
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
            # 模拟 open_span 内部异常但降级为 None
            from contextlib import contextmanager

            @contextmanager
            def _degrade_span(name, input=None):
                yield None

            mockOpenSpan.side_effect = _degrade_span
            response = tavily_search("异常测试", max_results=2)

        # 业务结果不受 span 故障影响
        assert response.count == 1
        assert response.query == "异常测试"
