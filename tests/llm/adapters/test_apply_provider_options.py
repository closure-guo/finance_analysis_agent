# tests/llm/adapters/test_apply_provider_options.py
"""adapter 消费 provider_options + raw_* 默认超时注入测试（Task 2）。

apply_provider_options 是 provider_options 唯一消费点：registry schema
校验 → deepseek 特定 kwargs（extra_body.thinking / reasoning_effort）；
``suppress_temperature`` 是 adapter→gateway 的内部契约标志（deepseek
thinking=enabled 时不发送 temperature，对齐 legacy deep 分支）。
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import ValidationError

from finance_agent.llm.adapters.litellm_adapter import (
    apply_provider_options,
    raw_acompletion,
    raw_completion,
    raw_stream,
)
from finance_agent.llm.registry import get_profile_preset
from finance_agent.llm.types import ModelProfile


def _deepseek(**options: object) -> ModelProfile:
    """deepseek-official preset + 覆盖 provider_options。"""
    p = get_profile_preset("deepseek-official")
    return dataclasses.replace(p, provider_options=dict(options))


class TestApplyProviderOptions:
    def test_enabled_returns_extra_body_effort_and_suppress(self):
        out = apply_provider_options(_deepseek(thinking="enabled", reasoning_effort="max"))
        assert out == {
            "extra_body": {"thinking": {"type": "enabled"}},
            "reasoning_effort": "max",
            "suppress_temperature": True,
        }

    def test_disabled_no_suppress_temperature(self):
        out = apply_provider_options(_deepseek(thinking="disabled", reasoning_effort="low"))
        assert out["extra_body"] == {"thinking": {"type": "disabled"}}
        assert out["reasoning_effort"] == "low"
        assert "suppress_temperature" not in out

    def test_unset_thinking_omits_thinking_key_and_suppress(self):
        out = apply_provider_options(_deepseek(reasoning_effort="high"))
        assert out == {"reasoning_effort": "high"}

    def test_empty_options_returns_empty(self):
        assert apply_provider_options(_deepseek()) == {}

    def test_non_deepseek_returns_empty(self):
        assert apply_provider_options(get_profile_preset("ark-glm")) == {}

    def test_invalid_value_raises_validation_error(self):
        with pytest.raises(ValidationError):
            apply_provider_options(_deepseek(thinking="sometimes"))

    def test_unknown_key_raises_validation_error(self):
        with pytest.raises(ValidationError):
            apply_provider_options(_deepseek(temperature=0.5))

    def test_deepseek_without_extra_body_allowed_returns_empty(self):
        p = _deepseek(thinking="enabled")
        cap = dataclasses.replace(p.capability, extra_body_allowed=False)
        assert apply_provider_options(dataclasses.replace(p, capability=cap)) == {}


class TestRawTimeoutInjection:
    """incident 016/017 卡死防护：调用方未传 timeout 时注入默认超时。"""

    def _patch_completion(self, monkeypatch, captured):
        import litellm

        def fake_completion(**kwargs):
            captured.append(kwargs)
            return "resp"

        monkeypatch.setattr(litellm, "completion", fake_completion)

    def test_raw_completion_injects_default_timeout(self, monkeypatch):
        captured: list[dict] = []
        self._patch_completion(monkeypatch, captured)
        monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
        raw_completion(model="openai/m")
        assert captured[0]["timeout"] == 300.0

    def test_raw_stream_injects_default_timeout(self, monkeypatch):
        captured: list[dict] = []
        self._patch_completion(monkeypatch, captured)
        monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
        raw_stream(model="openai/m")
        assert captured[0]["timeout"] == 300.0
        assert captured[0]["stream"] is True

    def test_env_overrides_default_timeout(self, monkeypatch):
        captured: list[dict] = []
        self._patch_completion(monkeypatch, captured)
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")
        raw_completion(model="openai/m")
        assert captured[0]["timeout"] == 12.5

    def test_explicit_timeout_not_overwritten(self, monkeypatch):
        captured: list[dict] = []
        self._patch_completion(monkeypatch, captured)
        raw_completion(model="openai/m", timeout=42)
        assert captured[0]["timeout"] == 42

    def test_raw_acompletion_injects_default_timeout(self, monkeypatch):
        """async 路径同样注入请求级默认超时（review finding：旧 harness timeout=120 行为回归）。"""
        import asyncio

        import litellm

        captured: list[dict] = []

        async def fake_acompletion(**kwargs):
            captured.append(kwargs)
            return "resp"

        monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
        monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
        asyncio.run(raw_acompletion(model="openai/m"))
        assert captured[0]["timeout"] == 300.0

    def test_raw_acompletion_explicit_timeout_not_overwritten(self, monkeypatch):
        import asyncio

        import litellm

        captured: list[dict] = []

        async def fake_acompletion(**kwargs):
            captured.append(kwargs)
            return "resp"

        monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
        asyncio.run(raw_acompletion(model="openai/m", timeout=42))
        assert captured[0]["timeout"] == 42
