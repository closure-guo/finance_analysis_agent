"""工具调用 Langfuse span 测试。

验证 ReAct Agent 执行工具时创建 tool:{name} span。
"""

from unittest.mock import MagicMock, patch

import pytest

from finance_agent.harness import Agent, PermissionMode
from finance_agent.harness.llm_client import LLMResponse


class MockLLMClient:
    """模拟 LLM 客户端，按预设序列返回响应。"""

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
    """构造工具调用对象。"""
    from finance_agent.harness.types import ToolCallRequest

    return ToolCallRequest(id="call_test", name=name, arguments=arguments)


@pytest.fixture
def echo_tool():
    """简单的回显工具。"""

    async def echo(text: str) -> str:
        """回显输入文本

        Args:
            text: 要回显的文本
        """
        return f"echo: {text}"

    return echo


class TestToolCallSpan:
    """工具调用 span 可观测测试。"""

    @pytest.mark.asyncio
    async def test_tool_execution_creates_span(self, echo_tool):
        """工具执行时创建 tool:{name} span，记录 input 与 output。"""
        mockLlm = MockLLMClient(
            [
                [
                    LLMResponse(
                        reasoning_delta="查一下",
                        tool_calls=[_make_tool_call("echo", {"text": "hello"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="结果是 echo: hello", is_finished=True)],
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

        # create=True：RED 阶段 loop.py 尚未 import open_span 时也能拿到 mock，
        # 让断言失败（而非 AttributeError 报错）成为可观测的 RED 信号
        with patch("finance_agent.harness.loop.open_span", create=True) as mockOpenSpan:
            mockObs = MagicMock()
            mockOpenSpan.return_value.__enter__.return_value = mockObs
            async for _ in agent.run("测试"):
                pass

        # 验证 open_span 被调用，且 name 为 "tool:echo"
        mockOpenSpan.assert_called()
        spanNames = [(c.kwargs.get("name") or c.args[0]) for c in mockOpenSpan.call_args_list]
        assert "tool:echo" in spanNames
        # 验证 input 含 args
        toolCall = [
            c
            for c in mockOpenSpan.call_args_list
            if (c.kwargs.get("name") or c.args[0]) == "tool:echo"
        ][0]
        assert toolCall.kwargs.get("input", {}).get("args") == {"text": "hello"}
        # 验证 obs.update 被调用记录 output
        mockObs.update.assert_called()
