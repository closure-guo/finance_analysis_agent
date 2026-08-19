# src/finance_agent/llm/gateway.py
"""LLM Gateway 统一入口（delta 4.4，设计档案 §4/§14）。

本模块提供 trace 契约 metadata 构造与统一 complete 入口骨架；业务代码
应经 gateway（后续 5.1 薄壳转调），而不是直接 import litellm。
当前阶段实现 build_trace_metadata（可验收）+ complete_text 最小实现，
streaming/with_tools 在 5.1 薄壳转调时补全。
"""

from __future__ import annotations

from typing import Any

from finance_agent.llm.adapters.litellm_adapter import (
    ensure_litellm_runtime,
    guard_params_supported,
)
from finance_agent.llm.errors import LLMTimeoutError
from finance_agent.llm.resolver import resolve_profile
from finance_agent.llm.types import ModelProfile, Purpose


def build_trace_metadata(
    profile: ModelProfile,
    *,
    purpose: Purpose,
    finish_reason: str | None = None,
    repair_count: int = 0,
    fallback_from: str | None = None,
    degradation: str | None = None,
) -> dict:
    """构造 generation trace 契约字段（design 档案 §14）。"""
    return {
        "profile": profile.name,
        "provider": profile.provider,
        "model": profile.model,
        "purpose": purpose,
        "capability": {
            "tools": profile.capability.tools,
            "json_schema": profile.capability.json_schema,
        },
        "finish_reason": finish_reason,
        "repair_count": repair_count,
        "fallback_from": fallback_from,
        "degradation": degradation,
    }


def complete_text(
    messages: list[dict[str, Any]],
    *,
    purpose: Purpose = "deep",
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    llm_config: dict[str, Any] | None = None,
    temperature: float | None = None,
) -> tuple[str, dict]:
    """统一非流式 complete 入口（骨架；薄壳转调后扩展）。

    返回 (text, trace_metadata)。守卫关键参数、预算派生、错误归一
    由 adapter/guard/errors 承接口——业务仅面向本入口与返回 metadata。
    """
    profile = resolve_profile(purpose=purpose, llm_config=llm_config)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice="auto")
    from finance_agent.llm.adapters.litellm_adapter import (
        apply_provider_options,
        derive_output_budget,
        normalize_exception,
        raw_completion,
    )

    budget = derive_output_budget(profile.capability, requested=max_tokens)
    # provider_options 消费（§7.1）：merge 在 default_params 之后（可覆盖）；
    # ``suppress_temperature`` 是 adapter→gateway 内部契约标志：deepseek
    # thinking=enabled 时端点拒收 temperature（对齐 legacy deep 分支），不发。
    provider_kwargs = apply_provider_options(profile)
    suppress_temperature = bool(provider_kwargs.pop("suppress_temperature", False))
    request_kwargs: dict[str, Any] = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": budget,
        "api_key": profile.api_key,
        "api_base": profile.base_url,
        **(profile.default_params or {}),
        **provider_kwargs,
    }
    if not suppress_temperature and temperature is not None:
        request_kwargs["temperature"] = temperature
    try:
        resp = raw_completion(**request_kwargs)
        text = resp.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        raise normalize_exception(exc) from exc
    return text, build_trace_metadata(
        profile, purpose=purpose, finish_reason=resp.choices[0].finish_reason
    )


def complete_stream(
    messages: list[dict[str, Any]],
    *,
    purpose: Purpose = "deep",
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    llm_config: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    temperature: float | None = None,
):
    """统一流式 complete 入口（delta 5.1）：yield CanonicalEvent。

    Agent 核心消费归一事件流（reasoning/text/finished/error），不感知
    provider 细节。对接 litellm 同步流 chunk（choices[0].delta:
    reasoning_content -> reasoning；content -> text）。

    ``trace``（可选）开启 Langfuse generation 观测：``{"name","metadata"}``。
    观测收口在 gateway（自 legacy.call_llm_stream 移植），调用方传入
    观测元数据，core 不直接触 Langfuse；不传则不观测（纯净接口）。
    """
    from finance_agent.llm.types import CanonicalEvent

    profile = resolve_profile(purpose=purpose, llm_config=llm_config)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice="auto")
    from finance_agent.llm.adapters.litellm_adapter import (
        apply_provider_options,
        classify_outcome,
        derive_output_budget,
        normalize_exception,
        raw_stream,
    )

    # Langfuse observation（可选）：观测收口（B1），结束前 update 根 span
    # output（incident #67：root span output 必须在 span exit/flush 前写）。
    _lf = None
    _gen_cm = None
    _gen = None
    if trace:
        from finance_agent.langfuse_tracing import get_langfuse

        _lf = get_langfuse()
        if _lf is not None:
            try:
                _gen_cm = _lf.start_as_current_observation(
                    as_type="generation",
                    name=trace.get("name") or f"litellm:{profile.model}",
                    model=profile.model,
                    input={"messages": messages},
                    metadata=trace.get("metadata") or {},
                )
                _gen = _gen_cm.__enter__()
            except Exception:  # noqa: S110 -- 观测失败不阻断业务
                _gen = None
                _gen_cm = None

    budget = derive_output_budget(profile.capability, requested=max_tokens)
    # provider_options 消费（§7.1）：merge 在 default_params 之后（可覆盖）；
    # ``suppress_temperature`` 是 adapter→gateway 内部契约标志：deepseek
    # thinking=enabled 时端点拒收 temperature（对齐 legacy deep 分支），不发。
    provider_kwargs = apply_provider_options(profile)
    suppress_temperature = bool(provider_kwargs.pop("suppress_temperature", False))
    request_kwargs: dict[str, Any] = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": budget,
        "api_key": profile.api_key,
        "api_base": profile.base_url,
        "tools": tools,
        **{k: v for k, v in (profile.default_params or {}).items() if k != "max_tokens"},
        **provider_kwargs,
    }
    if not suppress_temperature and temperature is not None:
        request_kwargs["temperature"] = temperature
    try:
        stream = raw_stream(**request_kwargs)
        saw_text = False
        finish = None
        _answer = ""
        _reasoning = ""
        _last_usage = None
        for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            finish = getattr(choice, "finish_reason", None) or finish
            if delta and hasattr(delta, "reasoning_content") and delta.reasoning_content:
                rc = str(delta.reasoning_content)
                _reasoning += rc
                yield CanonicalEvent(kind="reasoning", reasoning=rc)
            if delta and getattr(delta, "content", None):
                ct = str(delta.content)
                _answer += ct
                saw_text = True
                yield CanonicalEvent(kind="text", text=ct)
            if getattr(chunk, "usage", None):
                _last_usage = chunk.usage
        _finalize_observation(_gen, _answer, _reasoning, _last_usage)
        try:
            classify_outcome(finish, saw_text_delta=saw_text)
        except Exception as exc:  # noqa: BLE001
            yield CanonicalEvent(
                kind="error", finish_reason=type(exc).__name__, raw={"error": str(exc)}
            )
            return
        yield CanonicalEvent(kind="finished", finish_reason=finish)
    except Exception as exc:  # noqa: BLE001
        _finalize_observation(_gen, _answer, _reasoning, _last_usage)
        err = normalize_exception(exc)
        yield CanonicalEvent(
            kind="error", finish_reason=type(err).__name__, raw={"error": str(err)}
        )
    finally:
        if _gen_cm is not None:
            from contextlib import suppress

            with suppress(Exception):
                _gen_cm.__exit__(None, None, None)


def _finalize_observation(
    gen, answer: str, reasoning: str, last_usage, tool_calls: list | None = None
) -> None:
    """写 Langfuse generation output/usage（自 legacy 移植；无观测则 no-op）。

    incident #67：root span output 必须在 span exit/flush 前写，否则被丢弃。
    ``tool_calls``（可选）：``[{name, arguments}]`` 结构（自 harness 移植）。
    """
    if gen is None:
        return
    try:
        from finance_agent.langfuse_tracing import truncate_for_trace

        _ud = {}
        if last_usage is not None:
            _ud = {
                "input": getattr(last_usage, "prompt_tokens", 0) or 0,
                "output": getattr(last_usage, "completion_tokens", 0) or 0,
            }
        output: dict[str, Any] = {
            "answer": truncate_for_trace(answer),
            "reasoning": truncate_for_trace(reasoning),
        }
        if tool_calls:
            output["tool_calls"] = [
                {"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                for c in tool_calls
            ]
        gen.update(output=output, usage_details=_ud)
    except Exception:  # noqa: S110 -- 观测失败不阻断业务
        pass


async def complete_stream_async(
    messages: list[dict[str, Any]],
    *,
    purpose: Purpose = "deep",
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
    temperature: float | None = None,
    llm_config: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    chunk_timeout: float = 60.0,
    max_retries: int = 3,
    retry_delay: float = 1.0,
):
    """异步流式 complete 入口（delta 5.1-C Task 2）：yield CanonicalEvent。

    自 harness/litellm_client.chat_stream 移植的行为合同：per-chunk 超时
    （``asyncio.wait_for``）、可重试错误指数退避重试、重试耗尽/不可重试
    直接 raise（保 Agent 主循环捕获合同）、tool_calls 增量按 index 聚合
    终态产出单条 tool_call 事件。空输出分类不在本入口（loop 自有重试）。
    """
    import asyncio

    from finance_agent.llm.types import CanonicalEvent

    profile = resolve_profile(purpose=purpose, llm_config=llm_config)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice=tool_choice)
    from finance_agent.llm.adapters.litellm_adapter import (
        ToolCallAccumulator,
        apply_provider_options,
        derive_output_budget,
        finalize_tool_calls,
        normalize_exception,
        raw_acompletion,
        sanitize_request_messages,
    )

    messages = sanitize_request_messages(messages, profile.capability)

    # Langfuse observation（可选）：观测收口，结束前 update 根 span output
    _lf = None
    _gen_cm = None
    _gen = None
    if trace:
        from finance_agent.langfuse_tracing import get_langfuse

        _lf = get_langfuse()
        if _lf is not None:
            try:
                _gen_cm = _lf.start_as_current_observation(
                    as_type="generation",
                    name=trace.get("name") or f"litellm:{profile.model}",
                    model=profile.model,
                    input={"messages": messages},
                    metadata=trace.get("metadata") or {},
                )
                _gen = _gen_cm.__enter__()
            except Exception:  # noqa: S110 -- 观测失败不阻断业务
                _gen = None
                _gen_cm = None

    budget = derive_output_budget(profile.capability, requested=max_tokens)
    provider_kwargs = apply_provider_options(profile)
    suppress_temperature = bool(provider_kwargs.pop("suppress_temperature", False))
    request_kwargs: dict[str, Any] = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": budget,
        "api_key": profile.api_key,
        "api_base": profile.base_url,
        "tool_choice": tool_choice,
        **{k: v for k, v in (profile.default_params or {}).items() if k != "max_tokens"},
        **provider_kwargs,
    }
    if tools:
        request_kwargs["tools"] = tools
    if not suppress_temperature and temperature is not None:
        request_kwargs["temperature"] = temperature

    try:
        for attempt in range(max_retries):
            accumulator = ToolCallAccumulator()
            answer = ""
            reasoning_acc = ""
            last_usage = None
            try:
                resp = await raw_acompletion(**request_kwargs)
                _iter = resp.__aiter__()
                finish: str | None = None
                while True:
                    try:
                        chunk = await asyncio.wait_for(_iter.__anext__(), timeout=chunk_timeout)
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        raise _ChunkTimeoutError(
                            f"流式 chunk 超过 {chunk_timeout}s 未到达"
                        ) from None
                    if getattr(chunk, "usage", None):
                        last_usage = chunk.usage
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.delta
                    finish = getattr(choice, "finish_reason", None) or finish
                    if delta and getattr(delta, "reasoning_content", None):
                        rc = str(delta.reasoning_content)
                        reasoning_acc += rc
                        yield CanonicalEvent(kind="reasoning", reasoning=rc)
                    if delta and getattr(delta, "content", None):
                        ct = str(delta.content)
                        answer += ct
                        yield CanonicalEvent(kind="text", text=ct)
                    for t in getattr(delta, "tool_calls", None) or []:
                        accumulator.add(t)

                    if finish == "tool_calls" and accumulator.calls:
                        calls = finalize_tool_calls(accumulator)
                        _finalize_observation(
                            _gen,
                            answer,
                            reasoning_acc,
                            last_usage,
                            tool_calls=calls,
                        )
                        yield CanonicalEvent(kind="tool_call", tool_call={"calls": calls})
                        yield CanonicalEvent(kind="finished", finish_reason="tool_calls")
                        return
                    if finish == "stop":
                        if accumulator.calls:
                            calls = finalize_tool_calls(accumulator)
                            _finalize_observation(
                                _gen,
                                answer,
                                reasoning_acc,
                                last_usage,
                                tool_calls=calls,
                            )
                            yield CanonicalEvent(kind="tool_call", tool_call={"calls": calls})
                            yield CanonicalEvent(kind="finished", finish_reason="tool_calls")
                        else:
                            _finalize_observation(
                                _gen,
                                answer,
                                reasoning_acc,
                                last_usage,
                            )
                            yield CanonicalEvent(kind="finished", finish_reason="stop")
                        return

                # 流结束但无明确 finish_reason
                if accumulator.calls:
                    calls = finalize_tool_calls(accumulator)
                    _finalize_observation(
                        _gen,
                        answer,
                        reasoning_acc,
                        last_usage,
                        tool_calls=calls,
                    )
                    yield CanonicalEvent(kind="tool_call", tool_call={"calls": calls})
                    yield CanonicalEvent(kind="finished", finish_reason="tool_calls")
                else:
                    _finalize_observation(
                        _gen,
                        answer,
                        reasoning_acc,
                        last_usage,
                    )
                    yield CanonicalEvent(kind="finished", finish_reason=None)
                return
            except Exception as exc:  # noqa: BLE001
                err = normalize_exception(exc)
                if err.retryable and attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * 2**attempt)
                    continue
                raise err from exc
    finally:
        if _gen_cm is not None:
            from contextlib import suppress

            with suppress(Exception):
                _gen_cm.__exit__(None, None, None)


class _ChunkTimeoutError(LLMTimeoutError):
    """内部信号：per-chunk 超时（归一化后 retryable=True 参与重试）。"""
