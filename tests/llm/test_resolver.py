# tests/llm/test_resolver.py
"""ProfileResolver 唯一配置解析入口测试（Task 1.3）。

优先级：请求级 llm_config → 激活 profile → 环境变量 → registry 默认。
实战回归场景：judge 半套漂移（PR #74 修复的回退打错网关）、
「先 import 后 load_dotenv」时序、自定义端点前缀。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.resolver import (
    IncompleteLLMConfigError,
    UnknownProviderPrefixError,
    resolve_profile,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """隔离环境变量，测试不依赖 shell/.env。"""
    for var in (
        "LLM_MODEL",
        "LLM_QUICK_MODEL",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "JUDGE_MODEL",
        "JUDGE_BASE_URL",
        "JUDGE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


class TestPriorityOrder:
    def test_env_vars_build_profile(self):
        """环境变量齐全 → 构造 openai-compatible profile（openai/ 前缀补齐）。"""
        import os

        monkey: pytest.MonkeyPatch = pytest.MonkeyPatch()
        monkey.setenv("LLM_MODEL", "glm-5.2")  # 无前缀 + base_url → 强制 openai/
        monkey.setenv("LLM_BASE_URL", "https://ark.example/api/v3")
        monkey.setenv("LLM_API_KEY", "sk-test")
        profile = resolve_profile(purpose="deep", _env=os.environ)
        assert profile.model == "openai/glm-5.2"
        assert profile.base_url == "https://ark.example/api/v3"
        monkey.undo()

    def test_named_preset(self):
        profile = resolve_profile(purpose="judge", preset="deepseek-official", _env={})
        assert profile.provider == "deepseek"
        assert profile.capability.reasoning_must_echo_on_tool is True

    def test_request_level_overrides_env(self):
        """请求级 llm_config 完整时整体覆盖环境变量（原子切换）。"""
        import os

        monkey = pytest.MonkeyPatch()
        monkey.setenv("LLM_MODEL", "other-model")
        monkey.setenv("LLM_BASE_URL", "https://other.example/v1")
        monkey.setenv("LLM_API_KEY", "sk-env")
        llm_config = {
            "model": "glm-5.2",
            "baseUrl": "https://ark.example/api/v3",
            "apiKey": "sk-req",
        }
        profile = resolve_profile(purpose="deep", llm_config=llm_config, _env=os.environ)
        assert profile.model == "openai/glm-5.2"
        assert profile.api_key == "sk-req"
        monkey.undo()


class TestNoHalfConfigDrift:
    def test_partial_request_config_raises(self):
        """请求级只有 model 无端点凭据 → 显式报错，禁止与环境变量混搭。"""
        with pytest.raises(IncompleteLLMConfigError):
            resolve_profile(
                purpose="deep",
                llm_config={"model": "glm-5.2"},  # 缺 baseUrl/apiKey
                _env={"LLM_API_KEY": "sk-env", "LLM_BASE_URL": "https://env.example/v1"},
            )

    def test_judge_purpose_no_silent_fallback(self):
        """judge purpose 显式配置优先；环境缺 judge 配置时才用独立默认而非 LLM_*。

        实战回归：换 provider 后 JUDGE_* 回退 LLM_* 打错网关（28 项全败）。
        resolver 语义：judge 未配置时不得静默借用 LLM_BASE_URL。
        """
        with pytest.raises(IncompleteLLMConfigError):
            resolve_profile(
                purpose="judge",
                _env={"LLM_BASE_URL": "https://ark.example/v1", "LLM_API_KEY": "sk-llm"},
            )


class TestProviderPrefix:
    def test_unknown_prefix_rejected(self):
        """model 带未知 provider 前缀 → 显式报错（不从域名猜协议）。"""
        with pytest.raises(UnknownProviderPrefixError):
            resolve_profile(
                purpose="deep",
                _env={
                    "LLM_MODEL": "opencode/some-model",
                    "LLM_BASE_URL": "https://gw.example/v1",
                    "LLM_API_KEY": "k",
                },
            )

    def test_env_read_at_call_time(self):
        """配置必须调用时读环境（python -m 入口 import 早于 load_dotenv 的时序回归）。"""
        import os

        profile1 = resolve_profile(
            purpose="deep",
            _env={"LLM_MODEL": "glm-5.2", "LLM_BASE_URL": "https://a/v1", "LLM_API_KEY": "k1"},
        )
        assert profile1.model == "openai/glm-5.2"
        profile2 = resolve_profile(
            purpose="deep",
            _env={"LLM_MODEL": "glm-5.2", "LLM_BASE_URL": "https://b/v1", "LLM_API_KEY": "k1"},
        )
        assert profile2.base_url == "https://b/v1"
        del os
