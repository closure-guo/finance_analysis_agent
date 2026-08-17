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
) -> tuple[str, dict]:
    """统一非流式 complete 入口（骨架；薄壳转调后扩展）。

    返回 (text, trace_metadata)。守卫关键参数、预算派生、错误归一
    由 adapter/guard/errors 承接口——业务仅面向本入口与返回 metadata。
    """
    profile = resolve_profile(purpose=purpose, llm_config=llm_config)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice="auto")
    from finance_agent.llm.adapters.litellm_adapter import (
        derive_output_budget,
        normalize_exception,
        raw_completion,
    )

    budget = derive_output_budget(profile.capability, requested=max_tokens)
    try:
        resp = raw_completion(
            model=profile.model,
            messages=messages,
            max_tokens=budget,
            api_key=profile.api_key,
            api_base=profile.base_url,
            **(profile.default_params or {}),
        )
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
):
    """统一流式 complete 入口（delta 5.1）：yield CanonicalEvent。

    - text: 正文增量；reasoning: 思考增量；finished：流结束（带 finish_reason）；
      error：归一化 typed error。
    本骨架的 chunk 语义由 adapter.raw_stream 产出聚合；实际 chunk 结构
    在 legacy 流式转移时统一为 CanonicalEvent（当前 minimal 形态）。
    """
    profile = resolve_profile(purpose=purpose, llm_config=llm_config)
    ensure_litellm_runtime()
    guard_params_supported(profile.capability, tools=tools, tool_choice="auto")
    from finance_agent.llm.adapters.litellm_adapter import derive_output_budget, raw_stream

    budget = derive_output_budget(profile.capability, requested=max_tokens)
    try:
        stream = raw_stream(
            model=profile.model,
            messages=messages,
            max_tokens=budget,
            api_key=profile.api_key,
            api_base=profile.base_url,
            tools=tools,
            **{k: v for k, v in (profile.default_params or {}).items() if k != "max_tokens"},
        )
        saw_text = False
        finish = None
        for chunk in stream:
            # 兼容不同 chunk 形态：项优先取 content/delta，其次 choice delta
            delta = ""
            reasoning = ""
            finish = getattr(chunk, "finish", None) or finish
            if hasattr(chunk, "delta"):
                delta = chunk.delta or ""
            if hasattr(chunk, "reasoning"):
                reasoning = chunk.reasoning or ""
            if delta:
                saw_text = True
                yield {"kind": "text", "text": delta, "reasoning": "", "tool_call": None,
                       "finish_reason": None, "usage": None, "raw": None}
            if reasoning:
                yield {"kind": "reasoning", "text": "", "reasoning": reasoning,
                       "tool_call": None, "finish_reason": None, "usage": None, "raw": None}
        from finance_agent.llm.adapters.litellm_adapter import classify_outcome

        try:
            classify_outcome(finish, saw_text_delta=saw_text)
        except Exception as exc:  # noqa: BLE001
            yield {"kind": "error", "text": "", "reasoning": "", "tool_call": None,
                   "finish_reason": str(exc), "usage": None, "raw": str(exc)}
            return
        yield {"kind": "finished", "text": "", "reasoning": "", "tool_call": None,
               "finish_reason": finish, "usage": None, "raw": None}
    except Exception as exc:  # noqa: BLE001
        from finance_agent.llm.adapters.litellm_adapter import normalize_exception

        err = normalize_exception(exc)
        yield {"kind": "error", "text": "", "reasoning": "", "tool_call": None,
               "finish_reason": type(err).__name__, "usage": None, "raw": str(err)}
