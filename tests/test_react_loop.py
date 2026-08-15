"""Agent ReAct 循环测试。

用 mock LLM 验证 Agent.run() 的事件流：TOOL_CALL -> TOOL_RESULT -> ANSWER。
"""

from unittest.mock import patch

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
        # 第一次 LLM 调用：返回思考（reasoning_delta）+ 工具调用
        # 第二次 LLM 调用：返回最终回答（text_delta）
        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="我来帮你查一下",
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
        # （DeepSeek 思考模式：reasoning_delta -> THINK，text_delta -> ANSWER，原生分离）
        event_types = [e.event_type for e in events]
        assert ActionType.TOOL_CALL in event_types, f"缺少 TOOL_CALL，实际: {event_types}"
        assert ActionType.TOOL_RESULT in event_types, f"缺少 TOOL_RESULT，实际: {event_types}"
        assert ActionType.ANSWER in event_types, f"缺少 ANSWER，实际: {event_types}"
        # 工具调用前的思考应作为 THINK 流式输出（来自 reasoning_delta）
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
        # 直接回答：text_delta 作为 ANSWER 流式输出（DeepSeek 思考模式原生分离）
        assert ActionType.ANSWER in event_types, f"缺少 ANSWER，实际: {event_types}"
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
                    LLMResponse(reasoning_delta="我", is_finished=False),
                    LLMResponse(reasoning_delta="来", is_finished=False),
                    LLMResponse(reasoning_delta="查一下", is_finished=False),
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
        # "我来查一下" 拆成 3 个 reasoning_delta 增量 -> 至少 3 个 THINK 事件（逐 token 流式，非整段）
        assert len(think_events) >= 3, (
            f"思考未逐 token 流式：THINK 事件数 {len(think_events)}，期望 >= 3，"
            f"事件序列: {[e.event_type for e in events]}"
        )
        # 工具调用前的 3 个 THINK 文本可拼接还原原文
        pre_tool_think = "".join(e.content for e in think_events[:3])
        assert pre_tool_think == "我来查一下", f"思考文本不匹配: {pre_tool_think!r}"
        # 第二轮 text_delta 作为 ANSWER 流式输出（DeepSeek 思考模式原生分离）
        assert ActionType.ANSWER in [e.event_type for e in events]

    @pytest.mark.asyncio
    async def test_dsml_thinking_replaced_after_stream(self, echo_tool):
        """DSML 标记从 text 中清理后作为 ANSWER 下发，标记不泄漏给用户。

        DeepSeek 思考模式：DSML 标记出现在 content（text_delta）中，loop 安全
        流式跳过标记部分，流末解析为结构化工具调用并清理文本，清理后的安全部分
        作为 ANSWER 下发（不再发 THINK_REPLACE）。
        """
        bar = "\uff5c"  # 全角竖线 ｜
        dsml = (
            "让我查一下 "
            f"<{bar}{bar}DSML{bar}{bar}tool_calls>"
            f'<{bar}{bar}DSML{bar}{bar}invoke name="echo">'
            f'<{bar}{bar}DSML{bar}{bar}parameter name="text">hi</{bar}{bar}DSML{bar}{bar}parameter>'
            f"</{bar}{bar}DSML{bar}{bar}invoke>"
            f"</{bar}{bar}DSML{bar}{bar}tool_calls>"
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
        # 新版 reasoning/text 分离：DSML 标记从 text 中清理，安全部分作为 ANSWER 流式。
        # 验证所有 ANSWER 内容不含 DSML 标记/竖线（标记未泄漏给用户）。
        answer_events = [e for e in events if e.event_type == ActionType.ANSWER]
        answer_text = "".join(e.content for e in answer_events)
        assert "DSML" not in answer_text, f"ANSWER 仍含 DSML: {answer_text!r}"
        assert bar not in answer_text, f"ANSWER 仍含竖线标记: {answer_text!r}"

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


class TestReactLoopSpanMetadata:
    """重试 / DSML 防御性解析路径的 span metadata（trace-observability Task 6）。

    react_loop span 在 agent_factory 创建，loop.py 内经 OTel contextvar 自动定位；
    本组测试锁定 update_current_span 写入的 metadata 与 level。
    """

    @pytest.mark.asyncio
    async def test_empty_retry_reports_counts(self):
        """空输出重试触发后，span metadata 记 retries 计数，level=WARNING。"""
        captured = {}

        def _fake_update(metadata=None, level=None):
            captured["metadata"] = metadata
            captured["level"] = level

        # 第一次调用返回空输出（触发空输出重试），第二次返回最终回答
        mock_llm = MockLLMClient(
            [
                [LLMResponse(text_delta="", is_finished=True)],
                [LLMResponse(text_delta="完成", is_finished=True)],
            ]
        )
        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=3,
            llm=mock_llm,
        )

        with patch("finance_agent.harness.loop.update_current_span", new=_fake_update):
            events = []
            async for event in agent.run("测试"):
                events.append(event)

        # 重试后业务正常完成，且 metadata 记录重试计数
        assert ActionType.ANSWER in [e.event_type for e in events]
        assert captured["metadata"]["retries"]["empty"] == 1
        assert captured["metadata"]["retries"]["text_only"] == 0
        assert captured["level"] == "WARNING"

    @pytest.mark.asyncio
    async def test_dsml_fallback_reported(self, echo_tool):
        """DSML 防御性解析命中后，span metadata 记 dsml_fallback 与 count。"""
        captured = {}

        def _fake_update(metadata=None, level=None):
            captured["metadata"] = metadata
            captured["level"] = level

        bar = "\uff5c"  # 全角竖线 ｜
        dsml = (
            f"<{bar}{bar}DSML{bar}{bar}tool_calls>"
            f'<{bar}{bar}DSML{bar}{bar}invoke name="echo">'
            f'<{bar}{bar}DSML{bar}{bar}parameter name="text">hi</{bar}{bar}DSML{bar}{bar}parameter>'
            f"</{bar}{bar}DSML{bar}{bar}invoke>"
            f"</{bar}{bar}DSML{bar}{bar}tool_calls>"
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

        with patch("finance_agent.harness.loop.update_current_span", new=_fake_update):
            events = []
            async for event in agent.run("测试"):
                events.append(event)

        # DSML 被还原为工具调用（业务正常），且 metadata 记录降级事件
        assert ActionType.TOOL_CALL in [e.event_type for e in events]
        assert captured["metadata"]["degradation"] == "dsml_fallback"
        assert captured["metadata"]["count"] == 1
        assert captured["level"] == "WARNING"


def _make_tool_call(name: str, arguments: dict):
    """创建 ToolCallRequest 用于 mock。"""
    from finance_agent.harness.types import ToolCallRequest

    return ToolCallRequest(id="mock-1", name=name, arguments=arguments)
