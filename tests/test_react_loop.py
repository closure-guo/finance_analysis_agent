"""Agent ReAct 循环测试。

用 mock LLM 验证 Agent.run() 的事件流：TOOL_CALL -> TOOL_RESULT -> ANSWER。
"""

import pytest

from finance_agent.harness import ActionType, Agent, PermissionMode
from finance_agent.harness.llm_client import LLMResponse


class MockLLMClient:
    """模拟 LLM 客户端，按预设序列返回响应。"""

    def __init__(self, responses: list[list[LLMResponse]]):
        """每次 chat_stream 调用返回 responses[call_index] 中的 chunks。"""
        self._responses = responses
        self._call_index = 0
        self.last_messages: list[dict] | None = None
        self.last_tools: list[dict] | None = None

    async def chat_stream(self, messages=None, tools=None, temperature=0.7):
        self.last_messages = messages
        self.last_tools = tools
        if self._call_index >= len(self._responses):
            yield LLMResponse(text_delta="", is_finished=True)
            return
        chunks = self._responses[self._call_index]
        self._call_index += 1
        for chunk in chunks:
            yield chunk


@pytest.fixture
def echo_tool():
    """简单的回显工具，用于测试工具调用流程。"""

    async def echo(text: str) -> str:
        """回显输入文本

        Args:
            text: 要回显的文本
        """
        return f"echo: {text}"

    return echo


class TestReactLoop:
    """ReAct 循环事件流测试。"""

    @pytest.mark.asyncio
    async def test_tool_call_then_answer(self, echo_tool):
        """Agent 调用工具后给出最终回答。"""
        # 第一次 LLM 调用：返回工具调用
        # 第二次 LLM 调用：返回最终回答
        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        text_delta="我来帮你查一下",
                        tool_calls=[_make_tool_call("echo", {"text": "hello"})],
                        is_finished=True,
                    )
                ],
                [
                    LLMResponse(
                        text_delta="结果是: echo: hello",
                        is_finished=True,
                    )
                ],
            ]
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mock_llm,
        )
        agent.tools.register(echo_tool, name="echo")

        events = []
        async for event in agent.run("测试"):
            events.append(event)

        # 验证事件序列包含 TOOL_CALL, TOOL_RESULT, ANSWER
        event_types = [e.event_type for e in events]
        assert ActionType.TOOL_CALL in event_types, f"缺少 TOOL_CALL，实际: {event_types}"
        assert ActionType.TOOL_RESULT in event_types, f"缺少 TOOL_RESULT，实际: {event_types}"
        assert ActionType.ANSWER in event_types, f"缺少 ANSWER，实际: {event_types}"

        # TOOL_CALL 在 TOOL_RESULT 之前
        tc_idx = event_types.index(ActionType.TOOL_CALL)
        tr_idx = event_types.index(ActionType.TOOL_RESULT)
        assert tc_idx < tr_idx

        # 验证工具调用内容
        tool_call_event = events[tc_idx]
        assert tool_call_event.tool_call is not None
        assert tool_call_event.tool_call.name == "echo"

        # 验证工具结果内容
        tool_result_event = events[tr_idx]
        assert tool_result_event.tool_result is not None
        assert "echo: hello" in tool_result_event.tool_result.output

    @pytest.mark.asyncio
    async def test_no_tool_call_direct_answer(self):
        """LLM 不调用工具时直接回答。"""
        mock_llm = MockLLMClient(
            [
                [LLMResponse(text_delta="直接回答", is_finished=True)],
            ]
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=3,
            llm=mock_llm,
        )

        events = []
        async for event in agent.run("你好"):
            events.append(event)

        event_types = [e.event_type for e in events]
        assert ActionType.ANSWER in event_types
        assert ActionType.TOOL_CALL not in event_types

    @pytest.mark.asyncio
    async def test_max_iterations_truncation(self, echo_tool):
        """达到 max_iterations 时发出 ERROR 事件。"""
        # LLM 每次都返回工具调用，永不停止
        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        tool_calls=[_make_tool_call("echo", {"text": "loop"})],
                        is_finished=True,
                    )
                ],
            ]
            * 10
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=2,
            llm=mock_llm,
        )
        agent.tools.register(echo_tool, name="echo")

        events = []
        async for event in agent.run("循环测试"):
            events.append(event)

        event_types = [e.event_type for e in events]
        assert ActionType.ERROR in event_types, f"缺少 ERROR，实际: {event_types}"


def _make_tool_call(name: str, arguments: dict):
    """创建 ToolCallRequest 用于 mock。"""
    from finance_agent.harness.types import ToolCallRequest

    return ToolCallRequest(id="mock-1", name=name, arguments=arguments)
