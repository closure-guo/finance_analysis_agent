# tests/llm/test_gateway_stream_async.py
"""gateway complete_stream_async 测试（delta 5.1-C Task 2）。

mock raw_acompletion 返回 async iterable chunk 流，验证：
reasoning/text 事件、tool_call 增量合并、tool_choice 透传、
可重试退避、重试耗尽上抛、不可重试立即抛、per-chunk 超时。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import litellm
import pytest

from finance_agent.llm.errors import LLMError
from finance_agent.llm.gateway import complete_stream_async

CFG = {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"}


def _chunk(*, text="", reasoning="", tool_calls=None, finish=None):
    delta = SimpleNamespace(
        reasoning_content=reasoning or None,
        content=text or None,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


def _tc(index=0, id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._items:
            return self._items.pop(0)
        raise StopAsyncIteration


class _SlowAsyncIter:
    """每个 __anext__ 都 sleep，触发 per-chunk 超时。"""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(1)
        return _chunk(text="x")


async def _collect(coro_iter):
    return [ev async for ev in coro_iter]


async def test_reasoning_text_finished(monkeypatch):
    async def fake_acompletion(**kwargs):  # noqa: ARG001
        return _AsyncIter([_chunk(reasoning="思"), _chunk(text="答"), _chunk(finish="stop")])

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    events = await _collect(
        complete_stream_async([{"role": "user", "content": "hi"}], llm_config=CFG)
    )
    kinds = [e.kind for e in events]
    assert kinds == ["reasoning", "text", "finished"]
    assert events[-1].finish_reason == "stop"


async def test_tool_calls_merged_across_chunks(monkeypatch):
    async def fake_acompletion(**kwargs):  # noqa: ARG001
        return _AsyncIter(
            [
                _chunk(tool_calls=[_tc(id="call_0", name="get_price", arguments='{"s')]),
                _chunk(tool_calls=[_tc(arguments='ymbol": "000001"}')]),
                _chunk(finish="tool_calls"),
            ]
        )

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    events = await _collect(
        complete_stream_async([{"role": "user", "content": "hi"}], llm_config=CFG)
    )
    tc_events = [e for e in events if e.kind == "tool_call"]
    assert len(tc_events) == 1
    calls = tc_events[0].tool_call["calls"]
    assert len(calls) == 1
    assert calls[0]["id"] == "call_0"
    assert calls[0]["function"]["name"] == "get_price"
    import json

    assert json.loads(calls[0]["function"]["arguments"]) == {"symbol": "000001"}
    assert events[-1].kind == "finished"
    assert events[-1].finish_reason == "tool_calls"


async def test_finish_stop_with_tool_calls(monkeypatch):
    async def fake_acompletion(**kwargs):  # noqa: ARG001
        return _AsyncIter(
            [
                _chunk(tool_calls=[_tc(id="c1", name="f", arguments="{}")]),
                _chunk(finish="stop"),
            ]
        )

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    events = await _collect(
        complete_stream_async([{"role": "user", "content": "hi"}], llm_config=CFG)
    )
    assert [e.kind for e in events] == ["tool_call", "finished"]
    assert events[-1].finish_reason == "tool_calls"


async def test_tool_choice_passed_through(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _AsyncIter([_chunk(text="答", finish="stop")])

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    # 现有 preset 均未声明 tool_choice_required 能力，此用例只验证透传，
    # guard 行为由 test_gateway_params_guard 覆盖，这里 no-op guard。
    monkeypatch.setattr("finance_agent.llm.gateway.guard_params_supported", lambda *a, **kw: None)
    await _collect(
        complete_stream_async(
            [{"role": "user", "content": "hi"}],
            llm_config=CFG,
            tools=[{"type": "function", "function": {"name": "f"}}],
            tool_choice="required",
        )
    )
    assert captured["tool_choice"] == "required"
    assert captured["tools"][0]["function"]["name"] == "f"


async def test_retryable_error_then_success(monkeypatch):
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            raise litellm.exceptions.RateLimitError(
                message="limit", llm_provider="openai", model="m"
            )
        return _AsyncIter([_chunk(text="答", finish="stop")])

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    events = await _collect(
        complete_stream_async([{"role": "user", "content": "hi"}], llm_config=CFG, max_retries=3)
    )
    assert calls["n"] == 2
    assert events[-1].kind == "finished"


async def test_retry_exhaustion_raises(monkeypatch):
    async def fake_acompletion(**kwargs):  # noqa: ARG001
        raise litellm.exceptions.RateLimitError(message="limit", llm_provider="openai", model="m")

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(LLMError) as ei:
        await _collect(
            complete_stream_async(
                [{"role": "user", "content": "hi"}], llm_config=CFG, max_retries=2
            )
        )
    assert ei.value.retryable


async def test_non_retryable_raises_immediately(monkeypatch):
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):  # noqa: ARG001
        calls["n"] += 1
        raise litellm.exceptions.AuthenticationError(
            message="bad key", llm_provider="openai", model="m"
        )

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    with pytest.raises(LLMError) as ei:
        await _collect(complete_stream_async([{"role": "user", "content": "hi"}], llm_config=CFG))
    assert not ei.value.retryable
    assert calls["n"] == 1


async def test_per_chunk_timeout(monkeypatch):
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):  # noqa: ARG001
        calls["n"] += 1
        return _SlowAsyncIter()

    # 注意：不可 patch asyncio.sleep（_SlowAsyncIter 依赖真实 sleep 触发超时）
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    from finance_agent.llm.errors import LLMTimeoutError

    with pytest.raises(LLMTimeoutError):
        await _collect(
            complete_stream_async(
                [{"role": "user", "content": "hi"}],
                llm_config=CFG,
                chunk_timeout=0.05,
                max_retries=2,
                retry_delay=0.0,
            )
        )
    assert calls["n"] == 2


class TestStreamFlag:
    async def test_raw_acompletion_called_with_stream_true(self, monkeypatch):
        """流式必须下发 stream=True（否则拿到非流式 ModelResponse，无 __aiter__）。

        真实验证暴露：raw_acompletion 非流式返回 ModelResponse 非 async 迭代器，
        complete_stream_async 若漏传 stream=True 会在 __aiter__ 抛 AttributeError。
        """
        captured: dict = {}

        async def fake_raw(**kwargs):
            captured.update(kwargs)
            return _AsyncIter([_chunk(finish="stop")])

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_raw)
        events = await _collect(
            complete_stream_async(
                [{"role": "user", "content": "hi"}],
                llm_config={
                    "model": "deepseek/deepseek-chat",
                    "baseUrl": "https://api.deepseek.com/v1",
                    "apiKey": "k",
                },
            )
        )
        assert captured["stream"] is True
        assert any(e.kind == "finished" for e in events)
