"""LiteLLMClient.chat_stream 翻译层测试（delta 5.1-C Task 4）。

chat_stream 收口 gateway.complete_stream_async：本文件只测
CanonicalEvent→LLMResponse 翻译层语义（reasoning/text/tool_call/finished、
tool_call arguments json.loads + 坏 JSON 降级 {}、llm_config 完整性判定、
trace 元数据键）。

迁移映射（旧测试 → 新归属）：
- retry-raise / retry 次数 → tests/llm/test_gateway_stream_async.py（gateway 层）
- Langfuse output.reasoning/answer/tool_calls 落 trace → gateway 层（已覆盖）
- _build_kwargs thinking/deepseek 分支 → 已删除（provider options 归 adapter，
  见 tests/llm/adapters/test_apply_provider_options.py / test_message_sanitize.py）
- messages reasoning_content 清洗 / 单引号 arguments 规范化 → adapter
  （tests/llm/adapters/test_message_sanitize.py）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from finance_agent.harness.litellm_client import LiteLLMClient
from finance_agent.harness.llm_client import LLMResponse
from finance_agent.llm.errors import AuthError, ContentFilteredError
from finance_agent.llm.resolver import IncompleteLLMConfigError


@dataclass
class FakeEvent:
    kind: str
    text: str = ""
    reasoning: str = ""
    tool_call: dict[str, Any] | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


def _text_ev(t: str) -> FakeEvent:
    return FakeEvent(kind="text", text=t)


def _reasoning_ev(r: str) -> FakeEvent:
    return FakeEvent(kind="reasoning", reasoning=r)


def _tool_call_ev(calls: list[dict]) -> FakeEvent:
    return FakeEvent(kind="tool_call", tool_call={"calls": calls})


def _finished_ev() -> FakeEvent:
    return FakeEvent(kind="finished", finish_reason="stop")


class GatewayRecorder:
    """替换 gateway.complete_stream_async，记录调用参数并回放脚本事件。"""

    def __init__(self, events: list[FakeEvent]):
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        for ev in self.events:
            yield ev


async def _run(monkeypatch, client: LiteLLMClient, recorder: GatewayRecorder, **chat_kwargs):
    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", recorder)
    out: list[LLMResponse] = []
    async for r in client.chat_stream(messages=[{"role": "user", "content": "hi"}], **chat_kwargs):
        out.append(r)
    return out


# ── CanonicalEvent → LLMResponse 翻译 ──


@pytest.mark.asyncio
async def test_translates_text_and_reasoning_deltas(monkeypatch):
    rec = GatewayRecorder(
        [_reasoning_ev("思考A"), _reasoning_ev("思考B"), _text_ev("答案"), _finished_ev()]
    )
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    out = await _run(monkeypatch, client, rec)

    assert [r.reasoning_delta for r in out] == ["思考A", "思考B", "", ""]
    assert out[2].text_delta == "答案"
    assert out[2].is_finished is False
    # 纯文本结束：finished 事件 → 额外 is_finished=True 尾帧
    assert out[3].is_finished is True
    assert out[3].text_delta == ""


@pytest.mark.asyncio
async def test_translates_tool_call_event_with_parsed_arguments(monkeypatch):
    rec = GatewayRecorder(
        [
            _tool_call_ev(
                [
                    {
                        "id": "call_0",
                        "function": {"name": "web_search", "arguments": '{"q": "茅台"}'},
                    }
                ]
            ),
            _finished_ev(),
        ]
    )
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    out = await _run(monkeypatch, client, rec)

    assert out[0].is_finished is True
    assert out[0].tool_calls is not None
    assert out[0].tool_calls[0].id == "call_0"
    assert out[0].tool_calls[0].name == "web_search"
    # arguments 是 dict（ToolCallRequest 契约：已 JSON parse）
    assert out[0].tool_calls[0].arguments == {"q": "茅台"}
    # tool_call 帧已带 is_finished → finished 不再追加尾帧
    assert len(out) == 1


@pytest.mark.asyncio
async def test_tool_call_bad_json_falls_back_to_empty_dict(monkeypatch, caplog):
    rec = GatewayRecorder(
        [
            _tool_call_ev([{"id": "c1", "function": {"name": "f", "arguments": "{not-json"}}]),
            _finished_ev(),
        ]
    )
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    out = await _run(monkeypatch, client, rec)

    assert out[0].tool_calls[0].arguments == {}


@pytest.mark.asyncio
async def test_tool_call_missing_id_gets_index_fallback(monkeypatch):
    rec = GatewayRecorder(
        [
            _tool_call_ev(
                [
                    {"function": {"name": "a", "arguments": "{}"}},
                    {"id": "x", "function": {"name": "b", "arguments": "{}"}},
                ]
            ),
            _finished_ev(),
        ]
    )
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    out = await _run(monkeypatch, client, rec)

    assert [tc.id for tc in out[0].tool_calls] == ["call_0", "x"]


@pytest.mark.asyncio
async def test_error_event_not_expected_gateway_raises_instead(monkeypatch):
    """gateway 契约：重试耗尽 raise LLMError（不发 error 事件）。异常应透传。"""

    async def _raising(*args, **kwargs):
        raise RuntimeError("API 连接失败")
        yield  # pragma: no cover

    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", _raising)
    with pytest.raises(RuntimeError, match="API 连接失败"):
        async for _ in client.chat_stream(messages=[{"role": "user", "content": "t"}]):
            pass


# ── llm_config 完整性判定 / 参数透传 ──


@pytest.mark.asyncio
async def test_full_config_trio_passed_as_llm_config(monkeypatch):
    rec = GatewayRecorder([_text_ev("ok"), _finished_ev()])
    client = LiteLLMClient(
        model="deepseek/deepseek-chat",
        api_key="sk-fake",
        base_url="https://api.example.com/v1",
        max_retries=5,
        retry_delay=0.2,
    )
    await _run(
        monkeypatch,
        client,
        rec,
        tools=[{"type": "function", "function": {"name": "f"}}],
        temperature=0.3,
    )

    kw = rec.calls[0]
    assert kw["llm_config"] == {
        "model": "deepseek/deepseek-chat",
        "baseUrl": "https://api.example.com/v1",
        "apiKey": "sk-fake",
    }
    assert kw["purpose"] == "react"
    assert kw["max_retries"] == 5
    assert kw["retry_delay"] == 0.2
    assert kw["temperature"] == 0.3
    assert kw["tool_choice"] == "auto"
    assert kw["tools"] == [{"type": "function", "function": {"name": "f"}}]


@pytest.mark.asyncio
async def test_chat_stream_forwards_max_tokens_16384(monkeypatch):
    """harness ReAct 路径输出预算保真（终审 I1）：chat_stream 必须显式下发
    max_tokens=16384，避免请求级配置解析时回落到 openai-compatible 的 8192
    而截断 deep 输出（incident-016 类：reasoning 与正文共享配额）。"""
    rec = GatewayRecorder([_text_ev("ok"), _finished_ev()])
    client = LiteLLMClient(
        model="deepseek/deepseek-chat", api_key="sk-fake", base_url="https://api.example.com/v1"
    )
    await _run(monkeypatch, client, rec)
    assert rec.calls[0]["max_tokens"] == 16384


@pytest.mark.asyncio
async def test_partial_config_passes_none(monkeypatch):
    """构造参数不全（无显式 key、无 env key）时 llm_config=None，交给 resolver 用 env/preset。"""
    rec = GatewayRecorder([_text_ev("ok"), _finished_ev()])
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    client = LiteLLMClient(model="deepseek/deepseek-chat")
    await _run(monkeypatch, client, rec)
    assert rec.calls[0]["llm_config"] is None


# ── trace 元数据（镜像旧 _generation_metadata 语义）──


@pytest.mark.asyncio
async def test_trace_metadata_prompt_and_agent_keys(monkeypatch):
    rec = GatewayRecorder([_text_ev("ok"), _finished_ev()])
    client = LiteLLMClient(
        model="deepseek/deepseek-chat",
        api_key="fake",
        prompt_name="quick_mode",
        prompt_version=5,
        agent="react_agent",
    )
    await _run(monkeypatch, client, rec)

    trace = rec.calls[0]["trace"]
    assert trace["name"] == "react_agent"
    assert trace["metadata"] == {
        "prompt_name": "quick_mode",
        "prompt_version": 5,
        "agent": "react_agent",
    }


@pytest.mark.asyncio
async def test_trace_metadata_omits_unset_keys(monkeypatch):
    rec = GatewayRecorder([_text_ev("ok"), _finished_ev()])
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    await _run(monkeypatch, client, rec)

    trace = rec.calls[0]["trace"]
    assert trace["name"] == "litellm:deepseek/deepseek-chat"
    assert trace["metadata"] == {}


# ── 方舟文本格式工具调用识别（parse-ark-text-tool-call delta）──


@pytest.mark.asyncio
async def test_ark_text_tool_call_converted_to_structured(monkeypatch):
    """文本流中的 <tool_call> 块 SHALL 转为结构化调用，XML 不进正文。"""
    ark_text = (
        "深度分析管线首次调用返回空结果，我重试一次。<tool_call>run_deep_analysis"
        "<arg_key>stock_code</arg_key><arg_value>601700</arg_value>"
        "<arg_key>stock_name</arg_key><arg_value>风范股份</arg_value></tool_call>"
    )
    # 按 7 字符切块模拟标签跨增量分割
    events = [FakeEvent(kind="text", text=ark_text[i : i + 7]) for i in range(0, len(ark_text), 7)]
    events.append(_finished_ev())
    rec = GatewayRecorder(events)
    client = LiteLLMClient(model="deepseek/deepseek-chat", api_key="fake")
    out = await _run(monkeypatch, client, rec)

    joined_text = "".join(r.text_delta for r in out)
    assert "<tool_call>" not in joined_text, "XML 块不得漏进正文"
    assert joined_text.startswith("深度分析管线首次调用返回空结果，我重试一次。")

    tool_resp = [r for r in out if r.tool_calls]
    assert tool_resp, f"应产出结构化工具调用: {out}"
    call = tool_resp[0].tool_calls[0]
    assert call.name == "run_deep_analysis"
    assert call.arguments == {"stock_code": "601700", "stock_name": "风范股份"}
    assert tool_resp[0].is_finished is True


async def test_usage_forwarded_on_finished(monkeypatch):
    """#77：finished 事件的 usage 转发到 LLMResponse（预算校准的真值入口）。"""
    usage = {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}

    async def fake_stream(*a, **kw):  # noqa: ARG001
        yield FakeEvent(kind="text", text="答")
        yield FakeEvent(kind="finished", finish_reason="stop", usage=usage)

    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", fake_stream)
    client = LiteLLMClient(model="m", api_key="k", base_url="https://x/v1")
    chunks = [c async for c in client.chat_stream([{"role": "user", "content": "hi"}])]
    assert chunks[-1].is_finished
    assert chunks[-1].usage == usage


async def test_usage_forwarded_on_tool_calls(monkeypatch):
    """工具调用路径：usage 随 tool_calls 响应一起下发（循环 break 前能读到）。"""
    usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}

    async def fake_stream(*a, **kw):  # noqa: ARG001
        yield FakeEvent(
            kind="tool_call",
            tool_call={"calls": [{"id": "c1", "function": {"name": "echo", "arguments": "{}"}}]},
            usage=usage,
        )
        yield FakeEvent(kind="finished", finish_reason="tool_calls", usage=usage)

    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", fake_stream)
    client = LiteLLMClient(model="m", api_key="k", base_url="https://x/v1")
    chunks = [c async for c in client.chat_stream([{"role": "user", "content": "hi"}])]
    tc = next(c for c in chunks if c.tool_calls)
    assert tc.usage == usage


# ── fallback 链执行（spec llm-policy-router Requirement 2，#77 接线）────────


class ScriptedGateway:
    """按 handler(第几次调用, kwargs) 抛错或回放事件流的 complete_stream_async 替身。"""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        outcome = self.handler(len(self.calls), kwargs)
        for ev in outcome:
            yield ev


def _pin_primary(fallback: tuple[str, ...] = ("openai-official",)):
    """固定 primary=deepseek-official（隔离 env / probe 缓存对链解析的影响）。"""
    import dataclasses

    from finance_agent.llm.registry import get_profile_preset

    return patch(
        "finance_agent.llm.gateway.resolve_profile",
        return_value=dataclasses.replace(
            get_profile_preset("deepseek-official"), fallback=fallback
        ),
    )


async def _collect(client, **kw):
    return [c async for c in client.chat_stream([{"role": "user", "content": "hi"}], **kw)]


@pytest.mark.asyncio
async def test_auth_error_before_first_event_switches_to_fallback(monkeypatch):
    """连接阶段 typed error（零事件转发）→ 切链成员成功；切换事实落 trace。"""

    def handler(n, kw):
        if n == 1:
            raise AuthError("bad key")
        return [_finished_ev()]

    gw = ScriptedGateway(handler)
    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", gw)
    with _pin_primary():
        client = LiteLLMClient(model="m", api_key="k", base_url="https://x/v1")
        out = await _collect(client)

    assert out[-1].is_finished is True
    assert len(gw.calls) == 2
    # 首次尝试请求级配置透传（preset=None）；成员按 preset 名选中、不带请求级配置
    assert gw.calls[0]["preset"] is None
    assert gw.calls[1]["preset"] == "openai-official"
    assert gw.calls[1]["llm_config"] is None
    # 每次切换的 trace 记录 fallback_from + fallback_path（含完整路径）
    md1 = gw.calls[1]["trace"]["metadata"]
    assert md1["fallback_from"] == "deepseek-official"
    assert md1["fallback_path"] == ["deepseek-official", "openai-official"]
    assert "fallback_from" not in gw.calls[0]["trace"]["metadata"]


@pytest.mark.asyncio
async def test_no_chain_switch_after_events_forwarded(monkeypatch):
    """已向 Agent 转发事件后的触发错误照旧上抛（中途重启会重复下发内容）。"""

    class _OnceThenRaise:
        def __init__(self):
            self.calls = 0

        async def __call__(self, messages, **kwargs):
            self.calls += 1
            yield _text_ev("部分")
            yield _reasoning_ev("思考")
            raise ContentFilteredError("mid-stream blocked")

    raise_gen = _OnceThenRaise()
    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", raise_gen)
    client = LiteLLMClient(model="m", api_key="k", base_url="https://x/v1")
    with pytest.raises(ContentFilteredError):
        await _collect(client)
    assert raise_gen.calls == 1


@pytest.mark.asyncio
async def test_chain_resolution_failure_raises_original_error(monkeypatch):
    """链解析失败（配置半套等）→ 上抛原触发错误，不换错误面。"""

    def handler(n, kw):
        raise AuthError("bad key")

    gw = ScriptedGateway(handler)
    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", gw)

    def _broken_plan(*a, **kw):
        raise IncompleteLLMConfigError("半套配置")

    monkeypatch.setattr("finance_agent.llm.gateway.fallback_attempt_plan", _broken_plan)
    client = LiteLLMClient(model="m", api_key="k", base_url="https://x/v1")
    with pytest.raises(AuthError):
        await _collect(client)
    assert len(gw.calls) == 1


@pytest.mark.asyncio
async def test_happy_path_never_resolves_chain(monkeypatch):
    """happy path 不解析链（stub 与正常路径零额外成本）。"""

    async def fake_stream(*a, **kw):
        yield FakeEvent(kind="text", text="答")
        yield FakeEvent(kind="finished", finish_reason="stop")

    plan_mock = patch("finance_agent.llm.gateway.fallback_attempt_plan").start()
    monkeypatch.setattr("finance_agent.llm.gateway.complete_stream_async", fake_stream)
    client = LiteLLMClient(model="m", api_key="k", base_url="https://x/v1")
    out = await _collect(client)
    assert out[-1].is_finished is True
    assert plan_mock.call_count == 0
    patch.stopall()
