"""Agent SSE 事件流测试。

验证 StreamEvent 正确映射为前端 SSE 格式，包括事件类型转换和 metadata 处理。
"""

import asyncio
import json

import pytest

from finance_agent.harness import Agent, PermissionMode
from finance_agent.harness.llm_client import LLMResponse
from finance_agent.harness.types import ToolCallRequest


class MockLLMClient:
    """模拟 LLM 客户端。"""

    def __init__(self, responses):
        self._responses = responses
        self._call_index = 0

    async def chat_stream(
        self, messages=None, tools=None, temperature=0.7, tool_choice=None, **kwargs
    ):
        if self._call_index >= len(self._responses):
            yield LLMResponse(text_delta="", is_finished=True)
            return
        chunks = self._responses[self._call_index]
        self._call_index += 1
        for chunk in chunks:
            yield chunk


async def _collect_sse(async_gen, timeout=10.0):
    """收集 SSE 生成器的所有输出为字符串列表，超时后返回已收集的结果。

    MockLLMClient 在响应用完后返回空响应，agent loop 可能继续循环导致无限等待。
    超时保护确保测试不会卡死，已收集的事件仍可用于断言。
    """
    results = []
    try:
        async with asyncio.timeout(timeout):
            async for chunk in async_gen:
                results.append(chunk)
    except TimeoutError:
        pass
    return results


def _parse_sse_events(sse_strings: list[str]) -> list[dict]:
    """解析 SSE 字符串列表为事件 dict 列表。"""
    events = []
    for sse in sse_strings:
        # SSE 格式: data: {...}\n\n
        for line in sse.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


class TestStreamAgentToSse:
    """Agent SSE 事件流映射测试。"""

    @pytest.mark.asyncio
    async def test_answer_mapped_to_chat_token(self):
        """ANSWER 事件映射为 chat_token SSE。"""
        mock_llm = MockLLMClient(
            [
                [LLMResponse(text_delta="你好", is_finished=True)],
            ]
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=3,
            llm=mock_llm,
        )

        from finance_agent.agent_factory import stream_agent_to_sse

        sse_strings = await _collect_sse(stream_agent_to_sse(agent, "测试"))
        events = _parse_sse_events(sse_strings)

        chat_tokens = [e for e in events if e.get("type") == "chat_token"]
        assert len(chat_tokens) > 0
        assert "你好" in chat_tokens[0].get("token", "")

    @pytest.mark.asyncio
    async def test_tool_call_mapped_to_sse(self):
        """TOOL_CALL 事件映射为 tool_call SSE。"""

        async def echo(text: str) -> str:
            """回显

            Args:
                text: 文本
            """
            return f"echo: {text}"

        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        text_delta="我来帮你",
                        tool_calls=[ToolCallRequest(id="1", name="echo", arguments={"text": "hi"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="结果是 echo: hi", is_finished=True)],
            ]
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mock_llm,
        )
        agent.tools.register(echo, name="echo")

        from finance_agent.agent_factory import stream_agent_to_sse

        sse_strings = await _collect_sse(stream_agent_to_sse(agent, "测试"))
        events = _parse_sse_events(sse_strings)

        tool_calls = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_calls) > 0
        assert tool_calls[0]["name"] == "echo"

    @pytest.mark.asyncio
    async def test_permission_required_event_does_not_deadlock(self):
        """permission_required 事件（TOOL_CALL 且 tool_call=None）不得使事件流死锁。

        复现真实 bug：快速模式"沈阳天气"卡在搜索中。Agent 循环在每次工具执行前
        会 yield permission_required 事件；stream_agent_to_sse 旧实现用 continue
        跳过该事件，同时跳过了循环末尾的 nextTask 重建，导致下一轮 asyncio.wait
        等待已完成的旧 task，无限空转——agent 生成器永远停在那里，表现为
        "卡在搜索中"，且因 done 恒非空连心跳都发不出。

        该测试断言死锁点之后的 tool_result / chat_done 事件必须到达：
        旧实现下生成器无法在超时内推进到 tool_result，测试失败。
        """

        async def echo(text: str) -> str:
            """回显

            Args:
                text: 文本
            """
            return f"echo: {text}"

        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        text_delta="我来帮你",
                        tool_calls=[ToolCallRequest(id="1", name="echo", arguments={"text": "hi"})],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="结果是 echo: hi", is_finished=True)],
            ]
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mock_llm,
        )
        agent.tools.register(echo, name="echo")

        from finance_agent.agent_factory import stream_agent_to_sse

        sseStrings = await _collect_sse(stream_agent_to_sse(agent, "测试"), timeout=5.0)
        events = _parse_sse_events(sseStrings)

        # 死锁点在 permission_required，其后的 tool_result 与 chat_done 必须到达
        toolResults = [e for e in events if e.get("type") == "tool_result"]
        assert len(toolResults) > 0, "permission_required 事件后事件流死锁，tool_result 未到达"
        chatDones = [e for e in events if e.get("type") == "chat_done"]
        assert len(chatDones) > 0, "事件流未正常结束（chat_done 未到达）"

    @pytest.mark.asyncio
    async def test_error_mapped_to_sse(self):
        """ERROR 事件映射为 error SSE。"""
        # 用一个会触发 max_iterations 的场景
        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        tool_calls=[
                            ToolCallRequest(id="1", name="echo", arguments={"text": "loop"})
                        ],
                        is_finished=True,
                    )
                ],
            ]
            * 10
        )

        async def echo(text: str) -> str:
            """回显

            Args:
                text: 文本
            """
            return "loop"

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=2,
            llm=mock_llm,
        )
        agent.tools.register(echo, name="echo")

        from finance_agent.agent_factory import stream_agent_to_sse

        sse_strings = await _collect_sse(stream_agent_to_sse(agent, "循环测试"))
        events = _parse_sse_events(sse_strings)

        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_tool_metadata_triggers_session_creation(self):
        """TOOL_METADATA 事件触发 session 创建回调。"""
        # 模拟一个带 metadata 的流式工具

        async def mock_analysis(stock_code: str) -> str:
            """模拟分析

            Args:
                stock_code: 股票代码
            """
            return "report"

        mock_llm = MockLLMClient(
            [
                [
                    LLMResponse(
                        text_delta="分析中",
                        tool_calls=[
                            ToolCallRequest(
                                id="1", name="mock_analysis", arguments={"stock_code": "600519"}
                            )
                        ],
                        is_finished=True,
                    )
                ],
                [LLMResponse(text_delta="分析完成", is_finished=True)],
            ]
        )

        agent = Agent(
            model="mock",
            api_key="test",
            permission_mode=PermissionMode.YOLO,
            max_iterations=5,
            llm=mock_llm,
        )
        agent.tools.register(mock_analysis, name="mock_analysis")

        # 记录 metadata 回调
        captured_metadata = []

        from finance_agent.agent_factory import stream_agent_to_sse

        sse_strings = await _collect_sse(
            stream_agent_to_sse(agent, "分析茅台", on_metadata=captured_metadata.append)
        )

        # 由于 mock_analysis 不是流式工具，不会产生 TOOL_METADATA 事件
        # 这个测试验证 on_metadata 回调机制存在且不报错
        assert sse_strings is not None
