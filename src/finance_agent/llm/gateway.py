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
