# tests/llm/test_provider_options.py
"""provider_options 机制测试（设计档案 §7.1）。

三层合并：registry DEFAULT_PROVIDER_OPTIONS < env（命名 profile 级）
< 请求级 llm_config 白名单字段。消费只发生在 adapter。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.registry import (
    DEFAULT_PROVIDER_OPTIONS,
    PROVIDER_OPTIONS_SCHEMAS,
    REQUEST_OVERRIDABLE,
    get_profile_preset,
)
from finance_agent.llm.resolver import IncompleteLLMConfigError, resolve_profile


class TestRegistryProviderOptions:
    def test_deepseek_defaults_present(self):
        """deepseek 静态默认对齐 legacy deep 分支：thinking enabled + effort max。"""
        assert DEFAULT_PROVIDER_OPTIONS["deepseek"] == {
            "thinking": "enabled",
            "reasoning_effort": "max",
        }

    def test_deepseek_schema_validates(self):
        opts = PROVIDER_OPTIONS_SCHEMAS["deepseek"].model_validate(
            {"thinking": "disabled", "reasoning_effort": "low"}
        )
        assert opts.thinking == "disabled"
        assert opts.reasoning_effort == "low"

    def test_deepseek_schema_rejects_unknown(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PROVIDER_OPTIONS_SCHEMAS["deepseek"].model_validate({"foo": "bar"})

    def test_request_overridable_whitelist(self):
        assert REQUEST_OVERRIDABLE["deepseek"] == {"thinking", "reasoning_effort"}
        # 未登记 provider 白名单为空（请求级不可覆盖）
        assert "openai" not in REQUEST_OVERRIDABLE or not REQUEST_OVERRIDABLE["openai"]

    def test_model_profile_has_provider_options_field(self):
        profile = get_profile_preset("deepseek-official")
        assert profile.provider_options.get("thinking") == "enabled"

    def test_unknown_provider_no_defaults(self):
        assert DEFAULT_PROVIDER_OPTIONS.get("anthropic", {}) == {}


class TestResolverMerge:
    """合并优先级：registry defaults < env 覆盖 < 请求级白名单覆盖。"""

    def test_env_deepseek_gets_defaults(self):
        profile = resolve_profile(
            _env={
                "LLM_MODEL": "deepseek/deepseek-chat",
                "LLM_BASE_URL": "https://api.deepseek.com/v1",
                "LLM_API_KEY": "k",
            }
        )
        assert profile.provider_options == {
            "thinking": "enabled",
            "reasoning_effort": "max",
        }

    def test_env_overrides_defaults(self):
        profile = resolve_profile(
            _env={
                "LLM_MODEL": "deepseek/deepseek-chat",
                "LLM_BASE_URL": "https://api.deepseek.com/v1",
                "LLM_API_KEY": "k",
                "LLM_THINKING": "disabled",
                "LLM_REASONING_EFFORT": "low",
            }
        )
        assert profile.provider_options["thinking"] == "disabled"
        assert profile.provider_options["reasoning_effort"] == "low"

    def test_request_config_overrides_defaults(self):
        profile = resolve_profile(
            llm_config={
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://api.deepseek.com/v1",
                "apiKey": "k",
                "thinking": "disabled",
            }
        )
        assert profile.provider_options["thinking"] == "disabled"
        # 未覆盖字段保留 registry 默认
        assert profile.provider_options["reasoning_effort"] == "max"

    def test_request_non_whitelisted_key_rejected(self):
        with pytest.raises((ValueError, TypeError)):
            resolve_profile(
                llm_config={
                    "model": "deepseek/deepseek-chat",
                    "baseUrl": "https://api.deepseek.com/v1",
                    "apiKey": "k",
                    "provider_options": {"organization": "x"},
                }
            )

    def test_request_config_non_deepseek_no_options(self):
        profile = resolve_profile(
            llm_config={
                "model": "openai/gpt-4o",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            }
        )
        assert profile.provider_options == {}

    def test_incomplete_request_config_still_rejected(self):
        with pytest.raises(IncompleteLLMConfigError):
            resolve_profile(llm_config={"model": "deepseek/deepseek-chat", "apiKey": "k"})
