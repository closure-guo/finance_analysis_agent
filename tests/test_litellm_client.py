"""LiteLLM 客户端 chat_stream 错误传播测试。

对应 change: harden-react-path-resilience Task 2.1。
验证 chat_stream 重试耗尽后 SHALL raise 异常，而非 yield 错误文本。
"""

from __future__ import annotations

from unittest.mock import MagicMock

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


# ── tasks.md 3.4: LiteLLMClient thinking 配置测试 ──


def test_build_kwargs_thinking_default_enabled():
    """thinking=None 时 DeepSeek 模型默认 enabled（向后兼容）。"""
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    kwargs = client._build_kwargs(messages=[{"role": "user", "content": "hi"}])
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_build_kwargs_thinking_disabled():
    """thinking='disabled' 时 extra_body 设为 disabled。"""
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake", thinking="disabled")
    kwargs = client._build_kwargs(messages=[{"role": "user", "content": "hi"}])
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_build_kwargs_thinking_enabled_explicit():
    """thinking='enabled' 显式传入时 extra_body 设为 enabled。"""
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake", thinking="enabled")
    kwargs = client._build_kwargs(messages=[{"role": "user", "content": "hi"}])
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_build_kwargs_non_deepseek_ignores_thinking():
    """非 DeepSeek 模型不受 thinking 影响，走 temperature 模式。"""
    client = LiteLLMClient(model="openai/gpt-4o", api_key="fake", thinking="enabled")
    kwargs = client._build_kwargs(messages=[{"role": "user", "content": "hi"}])
    assert "extra_body" not in kwargs
    assert "temperature" in kwargs


def test_build_kwargs_thinking_with_tools():
    """thinking 配置下带 tools 时仍正确设置 extra_body。"""
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake", thinking="enabled")
    kwargs = client._build_kwargs(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "f"}}],
    )
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert kwargs["tools"] == [{"type": "function", "function": {"name": "f"}}]


def test_build_kwargs_base_url_from_init():
    """base_url 构造参数注入 api_base。"""
    client = LiteLLMClient(
        model="deepseek/deepseek-chat",
        api_key="fake",
        base_url="https://custom.example.com/v1",
    )
    kwargs = client._build_kwargs(messages=[{"role": "user", "content": "hi"}])
    assert kwargs["api_base"] == "https://custom.example.com/v1"


# ── agent-trace-content-fidelity Task 2: reasoning 落 generation output ──


@pytest.mark.asyncio
async def test_chat_stream_writes_reasoning_to_langfuse_output(monkeypatch):
    """流式 reasoning_content 累加并写入 generation output.reasoning。"""
    from finance_agent.harness.litellm_client import LiteLLMClient

    # 构造带 reasoning_content + content 的假流
    def _delta(reasoning=None, content=None):
        d = MagicMock()
        d.reasoning_content = reasoning
        d.content = content
        return d

    def _chunk(deltas, finish_reason=None):
        chunk = MagicMock()
        # usage 缺省 None；last_chunk.usage 为空由 _finish_langfuse 降级处理
        chunk.usage = None
        chunk.choices = [MagicMock(delta=deltas, finish_reason=finish_reason)]
        return chunk

    # litellm.acompletion(stream=True) 是 coroutine，await 后返回 async iterator。
    # 因此 mock 必须是 async function 返回 async generator（不能直接是 async generator）。
    async def _mock_acompletion(**kwargs):
        async def _stream():
            yield _chunk(_delta(reasoning="思考A"))
            yield _chunk(_delta(reasoning="思考B"))
            yield _chunk(_delta(content="最终答案"), finish_reason="stop")

        return _stream()

    monkeypatch.setattr("litellm.acompletion", _mock_acompletion)

    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)

    client = LiteLLMClient(model="deepseek-chat")
    monkeypatch.setattr(client, "_langfuse", MagicMock())
    client._langfuse.start_as_current_observation.return_value = mockCm

    results = []
    async for resp in client.chat_stream(messages=[{"role": "user", "content": "hi"}]):
        results.append(resp)

    # 断言 output 是对象且含累加的 reasoning
    mockObs.update.assert_called_once()
    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["reasoning"] == "思考A思考B"
    assert call_kwargs["output"]["answer"] == "最终答案"


@pytest.mark.asyncio
async def test_chat_stream_reasoning_empty_when_no_thinking(monkeypatch):
    """无 reasoning 时 output.reasoning 为空字符串。"""
    from finance_agent.harness.litellm_client import LiteLLMClient

    def _chunk(content, finish_reason="stop"):
        chunk = MagicMock()
        chunk.usage = None
        chunk.choices = [
            MagicMock(
                delta=MagicMock(content=content, reasoning_content=None),
                finish_reason=finish_reason,
            )
        ]
        return chunk

    async def _mock_acompletion(**kwargs):
        async def _stream():
            yield _chunk("纯文本答案")

        return _stream()

    monkeypatch.setattr("litellm.acompletion", _mock_acompletion)
    mockObs = MagicMock()
    mockCm = MagicMock()
    mockCm.__enter__ = MagicMock(return_value=mockObs)
    mockCm.__exit__ = MagicMock(return_value=False)
    client = LiteLLMClient(model="deepseek-chat")
    monkeypatch.setattr(client, "_langfuse", MagicMock())
    client._langfuse.start_as_current_observation.return_value = mockCm

    async for _ in client.chat_stream(messages=[{"role": "user", "content": "hi"}]):
        pass

    call_kwargs = mockObs.update.call_args.kwargs
    assert call_kwargs["output"]["reasoning"] == ""
    assert call_kwargs["output"]["answer"] == "纯文本答案"
