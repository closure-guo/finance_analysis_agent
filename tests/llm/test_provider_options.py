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

    def test_ark_glm_defaults_present(self):
        """ark-glm 官方默认：reasoning_effort=max（docs.bigmodel.cn）。"""
        assert DEFAULT_PROVIDER_OPTIONS["ark-glm"] == {"reasoning_effort": "max"}

    def test_ark_glm_schema_validates(self):
        opts = PROVIDER_OPTIONS_SCHEMAS["ark-glm"].model_validate({"reasoning_effort": "high"})
        assert opts.reasoning_effort == "high"
        opts2 = PROVIDER_OPTIONS_SCHEMAS["ark-glm"].model_validate({})
        assert opts2.reasoning_effort is None  # 未配置不强制覆盖

    def test_ark_glm_schema_rejects_unknown(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PROVIDER_OPTIONS_SCHEMAS["ark-glm"].model_validate({"thinking": "enabled"})

    def test_ark_glm_schema_rejects_invalid_effort(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PROVIDER_OPTIONS_SCHEMAS["ark-glm"].model_validate({"reasoning_effort": "ultra"})

    def test_ark_glm_request_overridable_whitelist(self):
        assert REQUEST_OVERRIDABLE["ark-glm"] == {"reasoning_effort"}


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

    def test_env_ark_glm_gets_defaults(self):
        """env 分支 model 含 glm → ark-glm 默认（reasoning_effort=max）。"""
        profile = resolve_profile(
            _env={
                "LLM_MODEL": "glm-5.3",
                "LLM_BASE_URL": "https://ark.example/api/v3",
                "LLM_API_KEY": "k",
            }
        )
        assert profile.provider_options == {"reasoning_effort": "max"}

    def test_env_ark_glm_overrides_defaults(self):
        profile = resolve_profile(
            _env={
                "LLM_MODEL": "glm-5.3",
                "LLM_BASE_URL": "https://ark.example/api/v3",
                "LLM_API_KEY": "k",
                "LLM_REASONING_EFFORT": "high",
            }
        )
        assert profile.provider_options["reasoning_effort"] == "high"

    def test_env_ark_glm_invalid_effort_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            resolve_profile(
                _env={
                    "LLM_MODEL": "glm-5.3",
                    "LLM_BASE_URL": "https://ark.example/api/v3",
                    "LLM_API_KEY": "k",
                    "LLM_REASONING_EFFORT": "ultra",
                }
            )

    def test_request_ark_glm_overrides_defaults(self):
        """请求级 reasoning_effort 覆盖 ark-glm 默认；未覆盖字段保留默认。"""
        profile = resolve_profile(
            llm_config={
                "model": "glm-5.3",
                "baseUrl": "https://ark.example/api/v3",
                "apiKey": "k",
                "reasoning_effort": "low",
            }
        )
        assert profile.provider_options == {"reasoning_effort": "low"}

    def test_request_ark_glm_defaults_when_not_set(self):
        profile = resolve_profile(
            llm_config={
                "model": "glm-5.3",
                "baseUrl": "https://ark.example/api/v3",
                "apiKey": "k",
            }
        )
        assert profile.provider_options == {"reasoning_effort": "max"}

    def test_request_ark_glm_invalid_effort_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            resolve_profile(
                llm_config={
                    "model": "glm-5.3",
                    "baseUrl": "https://ark.example/api/v3",
                    "apiKey": "k",
                    "reasoning_effort": "ultra",
                }
            )

    def test_request_ark_glm_top_level_thinking_ignored(self):
        """ark-glm 白名单只有 reasoning_effort：顶层 thinking 被忽略（不合并也不报错）。"""
        profile = resolve_profile(
            llm_config={
                "model": "glm-5.3",
                "baseUrl": "https://ark.example/api/v3",
                "apiKey": "k",
                "thinking": "enabled",
            }
        )
        assert profile.provider_options == {"reasoning_effort": "max"}

    def test_request_ark_glm_non_whitelisted_provider_options_rejected(self):
        with pytest.raises((ValueError, TypeError)):
            resolve_profile(
                llm_config={
                    "model": "glm-5.3",
                    "baseUrl": "https://ark.example/api/v3",
                    "apiKey": "k",
                    "provider_options": {"thinking": "enabled"},  # 不在白名单
                }
            )
