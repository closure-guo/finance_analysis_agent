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
