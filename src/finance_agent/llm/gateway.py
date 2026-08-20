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
from finance_agent.llm.errors import (
    AuthError,
    ContentFilteredError,
    LLMTimeoutError,
    ModelNotFoundError,
    OutputContractError,
    UnsupportedCapabilityError,
)
from finance_agent.llm.registry import get_profile_preset, list_presets
from finance_agent.llm.resolver import resolve_profile
from finance_agent.llm.router import select_profile
from finance_agent.llm.types import ModelProfile, Purpose


def _raw_completion_with_timeout(request_kwargs: dict[str, Any], timeout_seconds: float):
    """raw_completion 半僵连接兜底（incident 016/017 同族）。

    litellm 请求级 timeout 对挂死连接不触发——把阻塞调用放进 daemon 线程，
    主侧队列超时强制终止；超时抛 retryable LLMTimeoutError（调用方重试）。
    """
    import queue as _q
    import threading as _t

    q: _q.Queue = _q.Queue()

    def _call() -> None:
        try:
            from finance_agent.llm.adapters.litellm_adapter import raw_completion

            q.put(("ok", raw_completion(**request_kwargs)))
        except BaseException as exc:  # noqa: BLE001 -- 异常经队列回传
            q.put(("err", exc))

    _t.Thread(target=_call, daemon=True).start()
    try:
        status, item = q.get(timeout=timeout_seconds)
    except _q.Empty:
        from finance_agent.llm.errors import LLMTimeoutError

        raise LLMTimeoutError(
            f"非流式调用超过 {timeout_seconds}s 未返回（半僵连接），终止本次生成"
        ) from None
    if status == "err":
        raise item
    return item


def build_trace_metadata(
    profile: ModelProfile,
    *,
    purpose: Purpose,
    finish_reason: str | None = None,
    repair_count: int = 0,
    fallback_from: str | None = None,
    degradation: str | None = None,
    max_tokens_source: str | None = None,
    usage_estimated: bool | None = None,
) -> dict:
    """构造 generation trace 契约字段（design 档案 §14）。

    ``max_tokens_source``（"requested"|"capability"）与 ``usage_estimated``
    为可选预算治理观测键：仅显式传入时落入 dict，既有消费者不受影响。
    """
    meta = {
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
    if max_tokens_source is not None:
        meta["max_tokens_source"] = max_tokens_source
    if usage_estimated is not None:
        meta["usage_estimated"] = usage_estimated
    return meta


def _start_trace_observation(trace: dict[str, Any] | None, profile, messages):
    """按 trace dict 开启 Langfuse generation 观测（失败不阻断，返回 None）。"""
    if not trace:
        return None, None
    from finance_agent.langfuse_tracing import get_langfuse

    lf = get_langfuse()
    if lf is None:
        return None, None
    try:
        gen_cm = lf.start_as_current_observation(
            as_type="generation",
            name=trace.get("name") or f"litellm:{profile.model}",
            model=profile.model,
            input={"messages": messages},
            metadata=trace.get("metadata") or {},
        )
        return gen_cm, gen_cm.__enter__()
    except Exception:  # noqa: S110 -- 观测失败不阻断业务
        return None, None


def _usage_details(resp) -> dict:
    """resp.usage → Langfuse usage_details（无 usage 时空 dict）。"""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {}
    return {
        "input": getattr(usage, "prompt_tokens", 0) or 0,
        "output": getattr(usage, "completion_tokens", 0) or 0,
    }


def _extract_with_tools_output(resp) -> dict:
    """从 completion resp 提取结构化 generation output（自 legacy.py 移植）。

    返回 ``{answer, reasoning}``，非空 tool_calls 时追加 ``tool_calls`` 字段
    （``[{name, arguments}]``，arguments 裁剪）。answer 不回退 reasoning
    （工具调用场景 content 通常为空，回退会误导 trace）。
    """
    from finance_agent.langfuse_tracing import truncate_for_trace

    message = None
    choices = getattr(resp, "choices", [])
    if choices:
        message = getattr(choices[0], "message", None)
    output_text = (getattr(message, "content", "") or "") if message else ""
    reasoning_text = (getattr(message, "reasoning_content", "") or "") if message else ""
    tool_calls: list[dict] = []
    if message is not None:
        for tc in getattr(message, "tool_calls", None) or []:
            func = getattr(tc, "function", None)
            tc_name = (getattr(func, "name", "") or "") if func else ""
            tc_args = (getattr(func, "arguments", "") or "") if func else ""
            tool_calls.append({"name": tc_name, "arguments": truncate_for_trace(tc_args)})
    out: dict = {
        "answer": truncate_for_trace(output_text),
        "reasoning": truncate_for_trace(reasoning_text),
    }
    if tool_calls:
        out["tool_calls"] = tool_calls
    return out


def complete_text(
    messages: list[dict[str, Any]],
    *,
    purpose: Purpose = "deep",
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    llm_config: dict[str, Any] | None = None,
    preset: str | None = None,
    temperature: float | None = None,
    trace: dict[str, Any] | None = None,
    timeout_seconds: float = 300.0,
) -> tuple[str, dict]:
    """统一非流式 complete 入口（5.1-C：trace 观测 + sanitize + raw_* 元数据）。

    返回 ``(text, metadata)``：text 为 message.content（缺失空串，不做
    reasoning 回退）；metadata 除 trace 契约字段（build_trace_metadata）外
    附带 ``raw_content`` / ``raw_reasoning``（非 trace 字段，供 legacy 薄壳
    实现「content 为空回退 reasoning」旧行为）。
    ``timeout_seconds``：半僵连接兜底（incident 016/017 同族——请求级 300s
    超时对挂死连接不触发），非流式调用经 daemon 线程泵 + 队列超时强制终止
    （report/nlp/web_fetcher 全经此路径）。

    ``trace``（可选）开启 Langfuse generation 观测（name/metadata），
    观测失败不阻断业务；output 结构 ``{answer, reasoning}`` + usage_details。
    ``preset``：显式命名 preset（透传 resolve_profile，fallback 链成员用）。
    """
    profile = resolve_profile(purpose=purpose, llm_config=llm_config, preset=preset)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice="auto")
    from finance_agent.llm.adapters.litellm_adapter import (
        apply_provider_options,
        derive_output_budget,
        normalize_exception,
        sanitize_request_messages,
    )

    messages = sanitize_request_messages(messages, profile.capability)
    _gen_cm, _gen = _start_trace_observation(trace, profile, messages)

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
        **(profile.default_params or {}),
        **provider_kwargs,
    }
    if profile.api_key:
        request_kwargs["api_key"] = profile.api_key
    if profile.base_url:
        request_kwargs["api_base"] = profile.base_url
    if not suppress_temperature and temperature is not None:
        request_kwargs["temperature"] = temperature
    try:
        resp = _raw_completion_with_timeout(request_kwargs, timeout_seconds)
        message = resp.choices[0].message
        raw_content = message.content or ""
        raw_reasoning = getattr(message, "reasoning_content", "") or ""
    except Exception as exc:  # noqa: BLE001
        if _gen is not None:
            from contextlib import suppress

            with suppress(Exception):  # 观测失败不阻断
                _gen.update(metadata={"error_type": type(exc).__name__}, level="ERROR")
        _close_observation(_gen_cm)
        raise normalize_exception(exc) from exc
    # Langfuse output.answer 与 legacy call_llm 对齐：content 为空时用
    # reasoning 作为 answer（legacy trace 行为），但返回 text 不做回退。
    _finalize_observation(
        _gen,
        raw_content or raw_reasoning,
        raw_reasoning,
        getattr(resp, "usage", None),
        metadata=(trace or {}).get("metadata"),
    )
    _close_observation(_gen_cm)
    text = raw_content
    metadata = build_trace_metadata(
        profile,
        purpose=purpose,
        finish_reason=resp.choices[0].finish_reason,
        max_tokens_source="requested" if max_tokens is not None else "capability",
        # usage 真值存在时非估算（设计档案 §12：估算必须标 usage_estimated=true）
        usage_estimated=getattr(resp, "usage", None) is None,
    )
    metadata["raw_content"] = raw_content
    metadata["raw_reasoning"] = raw_reasoning
    return text, metadata


# fallback 链触发错误（spec llm-policy-router Requirement 2）：不可经同
# profile 重试解决的（合同耗尽/内容过滤/鉴权/模型缺失/能力不支持）依链
# 切换 profile；网络瞬时错误不在此处理（流路径内部自有重试）。
_FALLBACK_TRIGGER_ERRORS = (
    OutputContractError,
    ContentFilteredError,
    AuthError,
    ModelNotFoundError,
    UnsupportedCapabilityError,
)
_MAX_FALLBACK_ATTEMPTS = 3


def complete_text_with_fallback(
    messages: list[dict[str, Any]],
    *,
    purpose: Purpose = "deep",
    llm_config: dict[str, Any] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    trace: dict[str, Any] | None = None,
) -> tuple[str, dict]:
    """带 fallback 链的非流式 complete 入口（harden Task 4）。

    流程：resolve primary → 拼 candidates（primary + 其 registry fallback
    名）→ select_profile 排序/能力校验得重试链 → 逐成员调
    complete_text（primary 用请求级 llm_config 或命名 preset，fallback
    成员用 ``preset=<name>``）。捕获 ``_FALLBACK_TRIGGER_ERRORS``：
    链未耗尽换下一成员重试，成功后 metadata 合并 ``fallback_from``
    （前一 profile 名）+ ``router_trace``；链耗尽上抛最后错误；其他
    异常立即传播。总尝试次数 ≤3。业务调用点接线为 follow-up。
    """
    primary = resolve_profile(purpose=purpose, llm_config=llm_config)
    candidates: list[ModelProfile] = [primary]
    for name in primary.fallback:
        candidates.append(get_profile_preset(name))
    routed = select_profile(purpose=purpose, candidates=candidates)
    # 路由 primary 与请求解析 primary 一致时直接用其链；不一致仍以
    # 请求级 primary 打头（请求语义优先），链成员按路由序去重。
    ordered: list[ModelProfile] = [primary]
    for cand in [routed.primary, *routed.fallback_chain]:
        if all(cand.name != p.name for p in ordered):
            ordered.append(cand)
    ordered = ordered[:_MAX_FALLBACK_ATTEMPTS]

    preset_names = set(list_presets())
    last_error: Exception | None = None
    for idx, prof in enumerate(ordered):
        # 请求级 primary 优先透传 llm_config；命名 preset 成员用 preset 名
        use_config = llm_config if idx == 0 else None
        use_preset = prof.name if prof.name in preset_names else None
        try:
            text, metadata = complete_text(
                messages,
                purpose=purpose,
                max_tokens=max_tokens,
                llm_config=use_config if use_preset is None else None,
                preset=use_preset,
                temperature=temperature,
                trace=trace,
            )
        except _FALLBACK_TRIGGER_ERRORS as exc:
            last_error = exc
            if idx + 1 < len(ordered):
                continue
            raise
        if idx > 0:
            metadata["fallback_from"] = ordered[idx - 1].name
            metadata["router_trace"] = routed.trace
        return text, metadata
    raise last_error if last_error is not None else RuntimeError("fallback 链为空")


def _close_observation(gen_cm) -> None:
    """退出 Langfuse observation CM（失败不阻断）。"""
    if gen_cm is None:
        return
    from contextlib import suppress

    with suppress(Exception):
        gen_cm.__exit__(None, None, None)


def complete_with_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
    purpose: Purpose = "quick",
    max_tokens: int | None = None,
    temperature: float | None = None,
    llm_config: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
):
    """统一非流式带工具 complete 入口（5.1-C Task 3）。

    resolve_profile → guard → sanitize → budget → apply_provider_options →
    raw_completion，**返回原始 resp 对象**（调用方检查 ``.tool_calls``）。
    Langfuse 观测 output 含 ``{answer, reasoning, tool_calls?}`` + usage_details；
    主观测不可用时降级经 ``open_span`` 记录（对齐 legacy 降级路径）。

    计划内语义修正（5.1-C，零生产调用方）：deepseek thinking+tools 保持
    开启（registry provider_options 默认），不再像 legacy 显式 disabled。
    """
    from contextlib import suppress

    profile = resolve_profile(purpose=purpose, llm_config=llm_config)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice=tool_choice)
    from finance_agent.llm.adapters.litellm_adapter import (
        apply_provider_options,
        derive_output_budget,
        normalize_exception,
        raw_completion,
        sanitize_request_messages,
    )

    messages = sanitize_request_messages(messages, profile.capability)
    _gen_cm, _gen = _start_trace_observation(trace, profile, messages)

    budget = derive_output_budget(profile.capability, requested=max_tokens)
    provider_kwargs = apply_provider_options(profile)
    suppress_temperature = bool(provider_kwargs.pop("suppress_temperature", False))
    request_kwargs: dict[str, Any] = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": budget,
        **{k: v for k, v in (profile.default_params or {}).items() if k != "max_tokens"},
        **provider_kwargs,
    }
    if profile.api_key:
        request_kwargs["api_key"] = profile.api_key
    if profile.base_url:
        request_kwargs["api_base"] = profile.base_url
    if tools:
        request_kwargs["tools"] = tools
        if tool_choice:
            request_kwargs["tool_choice"] = tool_choice
    if not suppress_temperature and temperature is not None:
        request_kwargs["temperature"] = temperature

    def _do_call():
        try:
            return raw_completion(**request_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise normalize_exception(exc) from exc

    if trace and _gen is None:
        # 降级路径（对齐 legacy）：主观测不可用 → open_span（自带 no-op 兜底）
        from finance_agent.langfuse_tracing import open_span

        with open_span(
            name=trace.get("name") or f"litellm:{profile.model}",
            input={"messages": messages},
        ) as obs:
            resp = _do_call()
            if obs is not None:
                with suppress(Exception):  # trace 失败不影响业务
                    obs.update(output=_extract_with_tools_output(resp))
            _close_observation(_gen_cm)
            return resp

    resp = _do_call()
    if _gen is not None:
        with suppress(Exception):
            _gen.update(output=_extract_with_tools_output(resp), usage_details=_usage_details(resp))
    _close_observation(_gen_cm)
    return resp


def complete_stream(
    messages: list[dict[str, Any]],
    *,
    purpose: Purpose = "deep",
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    llm_config: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    temperature: float | None = None,
    chunk_timeout: float = 120.0,
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
        "api_base": profile.base_url,
        **{k: v for k, v in (profile.default_params or {}).items() if k != "max_tokens"},
        **provider_kwargs,
    }
    if profile.api_key:
        # keyless 本地端点（如 Ollama）api_key 为 None：不发送空 key
        request_kwargs["api_key"] = profile.api_key
    if tools:
        # tools 非空才携带：tools=None 下发会让方舟等式端点短思考后直接
        # finish=length（drop_params 白名单化后不再静默丢弃 None）——
        # evals 全节点 answer=0/truncation 的根因。
        request_kwargs["tools"] = tools
    if not suppress_temperature and temperature is not None:
        request_kwargs["temperature"] = temperature
    try:
        stream = raw_stream(**request_kwargs)
        saw_text = False
        finish = None
        _answer = ""
        _reasoning = ""
        _last_usage = None
        # per-chunk 超时保护（incident 016/017 卡死族）：同步阻塞迭代无法被
        # 中断，用 daemon 线程把 chunk 泵进队列、主侧带超时取——半僵流
        # （chunk 永不到达且 litellm 请求级 timeout 不触发）不再挂死进程。
        import queue as _queue
        import threading as _threading

        _DONE = object()
        _q: _queue.Queue = _queue.Queue()

        def _pump() -> None:
            try:
                for chunk in stream:
                    _q.put(chunk)
            except BaseException as exc:  # noqa: BLE001 -- 异常经队列回传主侧
                _q.put(exc)
            else:
                _q.put(_DONE)

        _threading.Thread(target=_pump, daemon=True).start()
        while True:
            try:
                item = _q.get(timeout=chunk_timeout)
            except _queue.Empty:
                from finance_agent.llm.errors import LLMTimeoutError

                raise LLMTimeoutError(
                    f"流式 chunk 超过 {chunk_timeout}s 未到达（半僵流），终止本次生成"
                ) from None
            if item is _DONE:
                break
            if isinstance(item, BaseException):
                raise item
            chunk = item
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
        _finalize_observation(
            _gen, _answer, _reasoning, _last_usage, metadata=(trace or {}).get("metadata")
        )
        try:
            classify_outcome(finish, saw_text_delta=saw_text)
        except Exception as exc:  # noqa: BLE001
            yield CanonicalEvent(
                kind="error", finish_reason=type(exc).__name__, raw={"error": str(exc)}
            )
            return
        yield CanonicalEvent(kind="finished", finish_reason=finish)
    except Exception as exc:  # noqa: BLE001
        _finalize_observation(
            _gen, _answer, _reasoning, _last_usage, metadata=(trace or {}).get("metadata")
        )
        err = normalize_exception(exc)
        if _gen is not None:
            from contextlib import suppress

            with suppress(Exception):  # noqa: S110 -- 观测失败不阻断
                _gen.update(metadata={"error_type": type(err).__name__}, level="ERROR")
        yield CanonicalEvent(
            kind="error", finish_reason=type(err).__name__, raw={"error": str(err)}
        )
    finally:
        if _gen_cm is not None:
            from contextlib import suppress

            with suppress(Exception):
                _gen_cm.__exit__(None, None, None)


def _finalize_observation(
    gen,
    answer: str,
    reasoning: str,
    last_usage,
    tool_calls: list | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """写 Langfuse generation output/usage（自 legacy 移植；无观测则 no-op）。

    incident #67：root span output 必须在 span exit/flush 前写，否则被丢弃。
    ``tool_calls``（可选）：``[{name, arguments}]`` 结构（自 harness 移植）。
    ``metadata``（可选）：显式经 update 写入——langfuse 4.13 OTel 导出会把
    start_as_current_observation(metadata=) 挤掉（观测 metadata 被 resource/
    scope 属性覆盖），业务标记（如 judge environment）必须在 update 时落。
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
        update_kwargs: dict[str, Any] = {"output": output, "usage_details": _ud}
        if metadata:
            update_kwargs["metadata"] = metadata
        gen.update(**update_kwargs)
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
        "api_base": profile.base_url,
        "tool_choice": tool_choice,
        # 关键：必须流式（raw_acompletion 非流式返回 ModelResponse 而非 async 迭代器）
        "stream": True,
        **{k: v for k, v in (profile.default_params or {}).items() if k != "max_tokens"},
        **provider_kwargs,
    }
    if profile.api_key:
        # keyless 本地端点（如 Ollama）api_key 为 None：不发送空 key
        request_kwargs["api_key"] = profile.api_key
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
                            metadata=(trace or {}).get("metadata"),
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
                                metadata=(trace or {}).get("metadata"),
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
                        metadata=(trace or {}).get("metadata"),
                    )
                    yield CanonicalEvent(kind="tool_call", tool_call={"calls": calls})
                    yield CanonicalEvent(kind="finished", finish_reason="tool_calls")
                else:
                    _finalize_observation(
                        _gen,
                        answer,
                        reasoning_acc,
                        last_usage,
                        metadata=(trace or {}).get("metadata"),
                    )
                    yield CanonicalEvent(kind="finished", finish_reason=None)
                return
            except Exception as exc:  # noqa: BLE001
                err = normalize_exception(exc)
                if err.retryable and attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * 2**attempt)
                    continue
                # 观测落痕：重试耗尽/不可重试上抛前写 error output（对齐旧 harness
                # _finish_langfuse 失败路径，避免错误 trace 静默）
                if _gen is not None:
                    from contextlib import suppress

                    with suppress(Exception):  # noqa: S110 -- 观测失败不阻断
                        _gen.update(
                            output={"error": str(err)},
                            level="ERROR",
                            metadata={"error_type": type(err).__name__},
                        )
                raise err from exc
    finally:
        if _gen_cm is not None:
            from contextlib import suppress

            with suppress(Exception):
                _gen_cm.__exit__(None, None, None)


class _ChunkTimeoutError(LLMTimeoutError):
    """内部信号：per-chunk 超时（归一化后 retryable=True 参与重试）。"""
