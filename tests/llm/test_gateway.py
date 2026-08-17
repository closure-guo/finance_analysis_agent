# tests/llm/test_gateway.py
"""LLM Gateway 统一入口 + trace 契约字段测试（delta 4.4）。

generation metadata 必须携带 provider 契约上下文
（design 档案 §14）：profile/provider/model/purpose/capability/
finish_reason/repair_count/fallback_from/degradation。
"""

from __future__ import annotations

from finance_agent.llm.gateway import build_trace_metadata
from finance_agent.llm.registry import get_profile_preset


def test_build_trace_metadata_basic_fields():
    profile = get_profile_preset("ark-glm")
    md = build_trace_metadata(profile, purpose="deep")
    assert md["profile"] == "ark-glm"
    assert md["provider"] == "openai"
    assert md["model"] == "openai/glm-5.2"
    assert md["purpose"] == "deep"
    assert md["capability"]["tools"] == "single"
    assert md["capability"]["json_schema"] == "json_mode"


def test_build_trace_optional_fields_default_to_none():
    profile = get_profile_preset("ark-glm")
    md = build_trace_metadata(profile, purpose="quick")
    assert md["finish_reason"] is None
    assert md["repair_count"] == 0
    assert md["fallback_from"] is None
    assert md["degradation"] is None


def test_build_trace_with_contract_facts():
    profile = get_profile_preset("deepseek-official")
    md = build_trace_metadata(
        profile,
        purpose="judge",
        finish_reason="tool_calls",
        repair_count=2,
        fallback_from="deepseek-official",
        degradation="action_protocol",
    )
    assert md["finish_reason"] == "tool_calls"
    assert md["repair_count"] == 2
    assert md["fallback_from"] == "deepseek-official"
    assert md["degradation"] == "action_protocol"
