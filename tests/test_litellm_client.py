"""LiteLLM 客户端 chat_stream 错误传播测试。

对应 change: harden-react-path-resilience Task 2.1。
验证 chat_stream 重试耗尽后 SHALL raise 异常，而非 yield 错误文本。
"""

from __future__ import annotations

import pytest

from finance_agent.harness.litellm_client import LiteLLMClient
from finance_agent.harness.llm_client import LLMResponse


@pytest.mark.asyncio
async def test_chat_stream_raises_on_retry_exhausted(monkeypatch):
    """chat_stream 重试耗尽后 SHALL raise 异常，不 yield 错误文本。"""
    client = LiteLLMClient(
        model="deepseek/deepseek-chat", api_key="fake", max_retries=2, retry_delay=0
    )

    # mock litellm.acompletion 持续抛出异常
    async def _mock_acompletion(**kwargs):
        raise RuntimeError("API 连接失败")

    monkeypatch.setattr("litellm.acompletion", _mock_acompletion)

    # 收集 yield 的所有 LLMResponse
    yielded: list[LLMResponse] = []
    with pytest.raises(RuntimeError, match="API 连接失败"):
        async for resp in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
            yielded.append(resp)

    # 不应 yield 任何包含错误文本的 LLMResponse
    assert len(yielded) == 0


@pytest.mark.asyncio
async def test_chat_stream_retries_before_raising(monkeypatch):
    """chat_stream SHALL 在重试次数内重试，耗尽后才 raise。"""
    callCount = 0
    client = LiteLLMClient(
        model="deepseek/deepseek-chat", api_key="fake", max_retries=3, retry_delay=0
    )

    async def _mock_acompletion(**kwargs):
        nonlocal callCount
        callCount += 1
        raise ConnectionError("网络错误")

    monkeypatch.setattr("litellm.acompletion", _mock_acompletion)

    with pytest.raises(ConnectionError, match="网络错误"):
        async for _ in client.chat_stream(messages=[{"role": "user", "content": "test"}]):
            pass

    # 应该重试 3 次（max_retries）
    assert callCount == 3
