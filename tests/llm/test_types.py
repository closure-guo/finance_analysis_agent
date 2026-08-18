# tests/llm/test_types.py
"""LLM Gateway 类型契约测试（add-llm-provider-gateway Task 1.1）。

Capability/ModelProfile 是防腐层核心：字段缺一则 provider 差异渗入业务。
场景字段以实战为准（incident 016/017、PR #74 七修复）。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.types import (
    CanonicalEvent,
    CanonicalRequest,
    Capability,
    ModelProfile,
)


def _capability(**overrides) -> Capability:
    base: dict = {
        "tools": "single",
        "tool_choice_required": False,
        "streaming": True,
        "streaming_tool_calls": True,
        "json_schema": "json_mode",
        "supports_system_role": True,
        "reasoning_field": "reasoning_content",
        "reasoning_must_echo_on_tool": False,
        "reasoning_forced": False,
        "max_context": 128000,
        "max_output": 8192,
        "extra_body_allowed": True,
    }
    base.update(overrides)
    return Capability(**base)


class TestCapability:
    def test_frozen(self):
        cap = _capability()
        with pytest.raises((AttributeError, TypeError)):  # frozen dataclass 赋值
            cap.tools = "parallel"  # type: ignore[misc]

    def test_reasoning_forced_ark_glm_profile(self):
        """方舟 GLM：思考强制开启不可关（disabled 400 拒）、不需回传。"""
        cap = _capability(
            reasoning_field="reasoning_content",
            reasoning_must_echo_on_tool=False,
            reasoning_forced=True,
        )
        assert cap.reasoning_forced is True

    def test_reasoning_echo_deepseek_profile(self):
        """DeepSeek 官方：工具轮次必须回传 reasoning_content（缺失 400）。"""
        cap = _capability(reasoning_must_echo_on_tool=True, reasoning_forced=False)
        assert cap.reasoning_must_echo_on_tool is True

    def test_reasoning_field_none_for_plain_models(self):
        """普通模型（如 OpenAI gpt-4o）无 reasoning 字段。"""
        cap = _capability(reasoning_field=None)
        assert cap.reasoning_field is None


class TestModelProfile:
    def test_frozen_with_defaults(self):
        profile = ModelProfile(
            name="ark-glm",
            provider="openai",
            model="openai/glm-5.2",
            base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
            api_key=None,
            capability=_capability(),
            default_params={"max_tokens": 16384},
        )
        assert profile.fallback == ()
        with pytest.raises((AttributeError, TypeError)):  # frozen dataclass 赋值
            profile.name = "x"  # type: ignore[misc]


class TestCanonicalTypes:
    def test_request_defaults(self):
        req = CanonicalRequest(messages=[{"role": "user", "content": "hi"}], purpose="deep")
        assert req.tool_choice == "auto"
        assert req.stream is False
        assert req.output_schema is None

    def test_event_kinds(self):
        text = CanonicalEvent(kind="text", text="答")
        reasoning = CanonicalEvent(kind="reasoning", reasoning="思考")
        finished = CanonicalEvent(kind="finished", finish_reason="stop")
        assert text.text == "答"
        assert reasoning.reasoning == "思考"
        assert finished.finish_reason == "stop"
