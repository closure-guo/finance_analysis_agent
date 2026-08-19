# tests/llm/test_gateway.py
"""LLM Gateway 统一入口 + trace 契约字段测试（delta 4.4）。

generation metadata 必须携带 provider 契约上下文
（design 档案 §14）：profile/provider/model/purpose/capability/
finish_reason/repair_count/fallback_from/degradation。
"""

from __future__ import annotations

from finance_agent.llm.gateway import build_trace_metadata, complete_text
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


class TestCompleteTextTemperatureAndProviderOptions:
    def _run(self, monkeypatch, llm_config, *, temperature=None):
        from types import SimpleNamespace

        captured = []

        def fake_completion(**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="答"), finish_reason="stop")
                ]
            )

        monkeypatch.setattr(
            "finance_agent.llm.adapters.litellm_adapter.raw_completion", fake_completion
        )
        complete_text(
            [{"role": "user", "content": "hi"}], llm_config=llm_config, temperature=temperature
        )
        return captured[0]

    def test_temperature_passed_through(self, monkeypatch):
        kw = self._run(
            monkeypatch,
            {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"},
            temperature=0.2,
        )
        assert kw["temperature"] == 0.2

    def test_deepseek_suppresses_temperature_and_sends_provider_kwargs(self, monkeypatch):
        kw = self._run(
            monkeypatch,
            {
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            },
            temperature=0.9,
        )
        assert kw["extra_body"] == {"thinking": {"type": "enabled"}}
        assert kw["reasoning_effort"] == "max"
        assert "temperature" not in kw
        assert "suppress_temperature" not in kw
