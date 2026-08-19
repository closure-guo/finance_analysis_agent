# src/finance_agent/llm/registry.py
"""provider 能力表（静态默认）。

静态表声明「我们已验证的默认行为」；capability probe（probes.py）是
运行时事实，冲突时以 probe 为准并写 warning（design 决策 7）。
行为依据：DeepSeek 官方文档（2025-12 起 thinking 支持工具调用、要求
回传 reasoning_content）与方舟 plan/v3 实测（incident 016/017、PR #74）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from finance_agent.llm.types import Capability, ModelProfile


class DeepSeekOptions(BaseModel):
    """deepseek provider_options schema（设计档案 §7.1 示例）。

    pydantic v2 默认 ignore 未知 key——本 schema 显式 extra="forbid"
    拒绝（未知配置项必须显式报错，禁止静默吞掉）。
    """

    model_config = ConfigDict(extra="forbid")

    thinking: Literal["enabled", "disabled"] | None = None
    reasoning_effort: Literal["low", "high", "max"] | None = None


# provider_options 校验 schema（§7.1 registry 静态三件套之一）
PROVIDER_OPTIONS_SCHEMAS: dict[str, type[BaseModel]] = {
    "deepseek": DeepSeekOptions,
}

# provider 静态默认 options（对齐 legacy deep 分支行为）
DEFAULT_PROVIDER_OPTIONS: dict[str, dict] = {
    "deepseek": {"thinking": "enabled", "reasoning_effort": "max"},
}

# 请求级 llm_config 允许覆盖的白名单；未登记 provider 请求级不可覆盖
REQUEST_OVERRIDABLE: dict[str, set[str]] = {
    "deepseek": {"thinking", "reasoning_effort"},
}

_NO_REASONING = {
    "reasoning_field": None,
    "reasoning_must_echo_on_tool": False,
    "reasoning_forced": False,
}


def _cap(**overrides: object) -> Capability:
    """BASE_CAP + 覆盖项构造 Capability（避免 ** 展开与显式 kwarg 冲突）。"""
    return Capability(**{**_BASE_CAP, **overrides})  # type: ignore[arg-type]


_BASE_CAP = {
    "tools": "single",
    "tool_choice_required": False,
    "streaming": True,
    "streaming_tool_calls": True,
    "json_schema": "json_mode",
    "supports_system_role": True,
    "max_context": 128000,
    "max_output": 8192,
    "extra_body_allowed": True,
}

_PRESETS: dict[str, ModelProfile] = {
    "deepseek-official": ModelProfile(
        name="deepseek-official",
        provider="deepseek",
        model="deepseek/deepseek-chat",
        base_url=None,
        api_key=None,
        # DeepSeek 官方：思考可关；工具轮次必须回传 reasoning_content
        capability=_cap(
            reasoning_field="reasoning_content",
            reasoning_must_echo_on_tool=True,
            reasoning_forced=False,
            # DeepSeek 官方支持 tool_choice=required（force_tool ReAct 轮）
            tool_choice_required=True,
        ),
        default_params={},
        provider_options=dict(DEFAULT_PROVIDER_OPTIONS["deepseek"]),
    ),
    "ark-glm": ModelProfile(
        name="ark-glm",
        provider="openai",
        model="openai/glm-5.2",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        api_key=None,
        # 方舟 GLM 实测：thinking 强制开启（disabled 被 400 拒）、effort 不透传、
        # 拒收 messages.reasoning_content 字段；reasoning 与正文共享 max_tokens
        capability=_cap(
            reasoning_field="reasoning_content",
            reasoning_must_echo_on_tool=False,
            reasoning_forced=True,
            # 方舟 GLM 支持函数调用 / tool_choice=required（force_tool ReAct 轮）
            tool_choice_required=True,
            # reasoning 与正文共享配额，预算必须覆盖 reasoning 峰值（incident 017）
            max_output=16384,
        ),
        default_params={"max_tokens": 16384},
    ),
    "openai-compatible": ModelProfile(
        name="openai-compatible",
        provider="openai",
        model="openai/<model>",
        base_url=None,  # 由调用方/环境注入
        api_key=None,
        # 通用 OpenAI 兼容端点（中转/Ollama/vLLM）：不做能力假设，
        # 上线前必须过 capability probe（llm-capability-probe spec）
        capability=_cap(**_NO_REASONING),
        default_params={},
    ),
    "openai-official": ModelProfile(
        name="openai-official",
        provider="openai",
        model="openai/gpt-4o",
        base_url=None,
        api_key=None,
        capability=_cap(**_NO_REASONING, tools="parallel", json_schema="strict_schema"),
        default_params={},
    ),
    "anthropic": ModelProfile(
        name="anthropic",
        provider="anthropic",
        model="anthropic/claude-sonnet-4",
        base_url=None,
        api_key=None,
        # adapter 负责 content block 归一，核心无感
        capability=_cap(**_NO_REASONING),
        default_params={},
    ),
}


def get_profile_preset(name: str) -> ModelProfile:
    """按名取静态 preset；未知名字抛 KeyError（不允许静默回退默认 provider）。"""
    return _PRESETS[name]


def list_presets() -> list[str]:
    return list(_PRESETS)
