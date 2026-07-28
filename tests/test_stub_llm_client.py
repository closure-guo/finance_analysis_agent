"""StubLLMClient 单元测试。"""

import asyncio

from finance_agent.harness.llm_client import LLMResponse
from finance_agent.harness.stub_llm_client import StubLLMClient


class TestStubLLMClient:
    """StubLLMClient 行为。"""

    def test_chat_stream_yields_fixed_text_deltas(self):
        """chat_stream 按固定节奏吐文本 delta。"""

        async def _run() -> list[LLMResponse]:
            client = StubLLMClient()
            chunks: list[LLMResponse] = []
            async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
                chunks.append(resp)
            return chunks

        chunks = asyncio.run(_run())

        # 至少吐出 2 个文本 delta
        text_deltas = [c for c in chunks if c.text_delta]
        assert len(text_deltas) >= 2
        # 所有文本 delta 拼接后有内容
        full_text = "".join(c.text_delta for c in text_deltas)
        assert len(full_text) > 0

    def test_chat_stream_ends_with_is_finished(self):
        """chat_stream 以 is_finished=True 结束。"""

        async def _run() -> list[LLMResponse]:
            client = StubLLMClient()
            chunks: list[LLMResponse] = []
            async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
                chunks.append(resp)
            return chunks

        chunks = asyncio.run(_run())

        assert chunks[-1].is_finished is True

    def test_chat_stream_no_tool_calls(self):
        """chat_stream 不返回 tool_calls（确保 ReAct Agent 1 轮完成）。"""

        async def _run() -> list[LLMResponse]:
            client = StubLLMClient()
            chunks: list[LLMResponse] = []
            async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
                chunks.append(resp)
            return chunks

        chunks = asyncio.run(_run())

        for c in chunks:
            assert c.tool_calls is None or len(c.tool_calls) == 0


class TestStubLLMClientToolCallScenario:
    """StubLLMClient 工具调用场景（STUB_SCENARIO=tool_call）。

    用于 E2E 确定性模拟"思考1 -> tool_call(web_search) -> 思考2 -> 回答"序列。
    默认无参构造仍保持 1 轮完成（见 TestStubLLMClient），本类验证显式启用
    工具调用场景后的行为。
    """

    def test_first_round_emits_thinking_then_tool_call(self):
        """第 1 轮：先吐思考1（reasoning_delta），再返回 tool_call(web_search)。"""

        async def _run() -> list[LLMResponse]:
            client = StubLLMClient(scenario="tool_call")
            chunks: list[LLMResponse] = []
            async for resp in client.chat_stream(
                messages=[{"role": "user", "content": "茅台最新消息"}],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
            ):
                chunks.append(resp)
            return chunks

        chunks = asyncio.run(_run())

        # 应先吐思考内容（reasoning_delta）
        reasoning = [c for c in chunks if c.reasoning_delta]
        assert len(reasoning) >= 1, "第 1 轮应吐思考1（reasoning_delta）"

        # 应返回 tool_call(web_search)
        tool_call_chunks = [c for c in chunks if c.tool_calls]
        assert len(tool_call_chunks) == 1, "第 1 轮应返回一次 tool_call"
        assert tool_call_chunks[0].tool_calls[0].name == "web_search"

        # 思考应在 tool_call 之前
        first_reasoning_idx = next(i for i, c in enumerate(chunks) if c.reasoning_delta)
        tool_call_idx = next(i for i, c in enumerate(chunks) if c.tool_calls)
        assert first_reasoning_idx < tool_call_idx, "思考1 应在 tool_call 之前"

    def test_second_round_emits_thinking_then_answer(self):
        """第 2 轮（工具结果已在上下文）：吐思考2（reasoning_delta）+ 回答（text_delta），不再调工具。"""

        async def _run() -> list[LLMResponse]:
            client = StubLLMClient(scenario="tool_call")
            # 模拟第 1 轮已完成（消费掉第 1 轮）
            async for _ in client.chat_stream(
                messages=[{"role": "user", "content": "茅台最新消息"}],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
            ):
                pass
            # 第 2 轮：上下文含工具结果
            chunks: list[LLMResponse] = []
            async for resp in client.chat_stream(
                messages=[
                    {"role": "user", "content": "茅台最新消息"},
                    {"role": "assistant", "content": "", "tool_calls": []},
                    {"role": "tool", "content": "搜索结果：茅台最新消息..."},
                ],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
            ):
                chunks.append(resp)
            return chunks

        chunks = asyncio.run(_run())

        # 第 2 轮应吐思考2 + 回答，不再返回 tool_call
        reasoning = [c for c in chunks if c.reasoning_delta]
        assert len(reasoning) >= 1, "第 2 轮应吐思考2（reasoning_delta）"
        text = [c for c in chunks if c.text_delta]
        assert len(text) >= 1, "第 2 轮应吐回答（text_delta）"
        for c in chunks:
            assert not c.tool_calls, "第 2 轮不应再返回 tool_call"

    def test_default_scenario_unchanged(self):
        """无参构造默认场景仍为 1 轮完成（不返回 tool_call）。"""

        async def _run() -> list[LLMResponse]:
            client = StubLLMClient()  # 无 scenario 参数
            chunks: list[LLMResponse] = []
            async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
                chunks.append(resp)
            return chunks

        chunks = asyncio.run(_run())

        for c in chunks:
            assert not c.tool_calls, "默认场景不应返回 tool_call"
