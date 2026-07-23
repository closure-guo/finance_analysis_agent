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

    async def chat_stream(self, messages=None, tools=None, temperature=0.7, tool_choice=None):
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

        # 验证事件序列包含 TOOL_CALL, TOOL_RESULT, THINK_TO_ANSWER
        # （最终回答不再发 ANSWER，改为 THINK_TO_ANSWER：思考已逐 token 流式，流末转为回答）
        event_types = [e.event_type for e in events]
        assert ActionType.TOOL_CALL in event_types, f"缺少 TOOL_CALL，实际: {event_types}"
        assert ActionType.TOOL_RESULT in event_types, f"缺少 TOOL_RESULT，实际: {event_types}"
        assert ActionType.THINK_TO_ANSWER in event_types, f"缺少 THINK_TO_ANSWER，实际: {event_types}"
        # 工具调用前的文本应作为 THINK 流式输出
        assert ActionType.THINK in event_types, f"缺少 THINK，实际: {event_types}"

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
        # 直接回答：文本作为 THINK 流式输出，流末转为 THINK_TO_ANSWER（不再发 ANSWER）
        assert ActionType.THINK_TO_ANSWER in event_types, f"缺少 THINK_TO_ANSWER，实际: {event_types}"
        assert ActionType.TOOL_CALL not in event_types

    @pytest.mark.asyncio
    async def test_thinking_streamed_token_by_token(self, echo_tool):
        """回归测试：思考过程应逐 token 流式输出（多个 THINK 事件），而非整段一个事件。

        根因：原实现将 LLM 文本整体缓冲到流末才发一个 THINK 事件，
        导致快速模式看不到思考过程的流式输出。
        """
        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(text_delta="我", is_finished=False),
                    LLMResponse(text_delta="来", is_finished=False),
                    LLMResponse(text_delta="查一下", is_finished=False),
                    LLMResponse(
                        tool_calls=[_make_tool_call("echo", {"text": "hi"})],
                        is_finished=True,
                    ),
                ],
                [
                    LLMResponse(text_delta="完成", is_finished=True),
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

        think_events = [e for e in events if e.event_type == ActionType.THINK]
        # "我来查一下" 拆成 3 个增量 -> 至少 3 个 THINK 事件（逐 token 流式，非整段）
        assert len(think_events) >= 3, (
            f"思考未逐 token 流式：THINK 事件数 {len(think_events)}，期望 >= 3，"
            f"事件序列: {[e.event_type for e in events]}"
        )
        # 工具调用前的 3 个 THINK 文本可拼接还原原文
        pre_tool_think = "".join(e.content for e in think_events[:3])
        assert pre_tool_think == "我来查一下", f"思考文本不匹配: {pre_tool_think!r}"
        # 第二轮回答应转为 THINK_TO_ANSWER（不再发 ANSWER）
        assert ActionType.THINK_TO_ANSWER in [e.event_type for e in events]

    @pytest.mark.asyncio
    async def test_dsml_thinking_replaced_after_stream(self, echo_tool):
        """DSML 标记流式输出后，流末应发 THINK_REPLACE 用清理后文本覆盖。"""
        BAR = "\uff5c"  # 全角竖线 ｜
        dsml = (
            "让我查一下 "
            f"<{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
            f"<{BAR}{BAR}DSML{BAR}{BAR}invoke name=\"echo\">"
            f"<{BAR}{BAR}DSML{BAR}{BAR}parameter name=\"text\">hi</{BAR}{BAR}DSML{BAR}{BAR}parameter>"
            f"</{BAR}{BAR}DSML{BAR}{BAR}invoke>"
            f"</{BAR}{BAR}DSML{BAR}{BAR}tool_calls>"
        )
        mock_llm = MockLLMClient(
            [
                [LLMResponse(text_delta=dsml, is_finished=True)],
                [LLMResponse(text_delta="完成", is_finished=True)],
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

        event_types = [e.event_type for e in events]
        # DSML 被还原为结构化工具调用
        assert ActionType.TOOL_CALL in event_types, f"DSML 未解析为工具调用: {event_types}"
        # 流末清理后发 THINK_REPLACE 覆盖原始 DSML 文本
        assert ActionType.THINK_REPLACE in event_types, f"缺少 THINK_REPLACE: {event_types}"
        replace_event = next(e for e in events if e.event_type == ActionType.THINK_REPLACE)
        assert "DSML" not in replace_event.content, f"THINK_REPLACE 仍含 DSML: {replace_event.content!r}"
        assert BAR not in replace_event.content, f"THINK_REPLACE 仍含竖线标记: {replace_event.content!r}"

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
