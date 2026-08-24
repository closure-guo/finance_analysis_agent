# src/finance_agent/llm/resolver.py
"""ProfileResolver：LLM 配置的唯一解析入口（design 决策 8）。

优先级：请求级 llm_config → 命名 preset → 环境变量 → registry 默认。

核心不变量：
- 原子性：请求级配置 model+baseUrl 必须齐全（缺 baseUrl 抛
  IncompleteLLMConfigError），apiKey 可省——keyless 本地端点（Ollama）
  或显式 env 回退（LLM_API_KEY → DEEPSEEK_API_KEY）。
  原 judge 回退 LLM_* 打错网关（PR #74）的混搭防线保留在 baseUrl 层。
- 调用时读环境：模块级不缓存任何环境值（python -m 入口 import 早于
  load_dotenv 的时序 bug 回归）。
- judge 不静默借用 LLM_*：评估裁判必须显式配置（JUDGE_*），或显式选择
  与主管线相同的命名 preset——不存在隐式回退。
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping
from typing import Any

from finance_agent.llm.registry import (
    _PRESETS,
    DEFAULT_PROVIDER_OPTIONS,
    PROVIDER_OPTIONS_SCHEMAS,
    REQUEST_OVERRIDABLE,
    ModelProfile,
    get_profile_preset,
)
from finance_agent.llm.types import Purpose

# registry 已知 provider（model 前缀白名单）
_KNOWN_PREFIXES = {"openai", "deepseek", "anthropic", "gemini"}

# judge purpose 的环境变量映射（与业务管线完全独立）
_JUDGE_ENV = {"model": "JUDGE_MODEL", "base_url": "JUDGE_BASE_URL", "api_key": "JUDGE_API_KEY"}
# 业务 purpose 的环境变量映射（quick 档位独立模型名）
_LLM_ENV = {"model": "LLM_MODEL", "base_url": "LLM_BASE_URL", "api_key": "LLM_API_KEY"}
_LLM_QUICK_ENV = {"model": "LLM_QUICK_MODEL", "base_url": "LLM_BASE_URL", "api_key": "LLM_API_KEY"}


class IncompleteLLMConfigError(ValueError):
    """半套配置（如只有 model 无端点/凭据）——禁止与环境变量混搭漂移。"""


class UnknownProviderPrefixError(ValueError):
    """model 前缀不在已知 provider 白名单——不从域名猜协议。"""


# API 形式 → provider 前缀（add-llm-api-form）：
# Chat Completion / Responses 走 OpenAI 系，Messages 走 Anthropic。
_API_FORM_PROVIDER = {"chat_completion": "openai", "responses": "openai", "messages": "anthropic"}


def _ensure_prefix(model: str, base_url: str | None, api_form: str | None = None) -> str:
    """自定义端点 + 无前缀 → openai/；已带前缀但未知 → 显式报错。"""
    if "/" in model:
        provider = model.split("/", 1)[0]
        if provider not in _KNOWN_PREFIXES:
            raise UnknownProviderPrefixError(
                f"未知 provider 前缀 '{provider}'。已知: {sorted(_KNOWN_PREFIXES)}；"
                "OpenAI 兼容端点请使用 openai/<model>"
            )
        return model
    # 裸模型名：按所选 API 形式推导 provider 前缀（用户不再手写 openai/anthropic）
    if api_form and api_form in _API_FORM_PROVIDER:
        return f"{_API_FORM_PROVIDER[api_form]}/{model}"
    if base_url:
        return f"openai/{model}"
    # 无端点也无前缀：交给 registry 默认 provider 语义（deepseek-official）
    return model


def _resolve_from_env(
    env: Mapping[str, str], mapping: dict[str, str]
) -> tuple[str, str | None, str | None]:
    model = env.get(mapping["model"], "")
    base_url = env.get(mapping["base_url"], "") or None
    api_key = env.get(mapping["api_key"], "") or None
    return model, base_url, api_key


def _validate_options(provider: str, options: dict[str, Any]) -> dict[str, Any]:
    """有 schema 的 provider 走 pydantic 校验（未知 key / 非法值显式报错）。"""
    schema = PROVIDER_OPTIONS_SCHEMAS.get(provider)
    if schema is not None:
        schema.model_validate(options)
    return options


def _provider_options_from_request(provider: str, llm_config: dict[str, Any]) -> dict[str, Any]:
    """请求级合并（§7.1）：registry defaults < llm_config 白名单字段。

    白名单来源两处：顶层白名单键（如 ``thinking``）+ 可选 ``provider_options``
    dict；白名单外的 key 抛 ValueError 家族，禁止请求级覆盖受管配置。

    ark 端点（model 含 glm）走 ark-glm 白名单——registry 白名单在
    "ark-glm" 名下，但 resolver 请求分支 provider 前缀是 "openai"
    （env:openai/glm-5.3 同理，model 名才是识别锚点）；其余走 provider 白名单。
    """
    raw_model = str(llm_config.get("model") or "")
    options_key = "ark-glm" if "glm" in raw_model.lower() else provider
    merged = dict(DEFAULT_PROVIDER_OPTIONS.get(options_key, {}))
    whitelist = REQUEST_OVERRIDABLE.get(options_key, set())
    for key in whitelist:
        if key in llm_config:
            merged[key] = llm_config[key]
    raw = llm_config.get("provider_options")
    if raw is not None:
        if not isinstance(raw, dict):
            raise IncompleteLLMConfigError("llm_config.provider_options 必须是 dict")
        for key, value in raw.items():
            if key not in whitelist:
                raise IncompleteLLMConfigError(
                    f"provider_options 键 '{key}' 不在 {options_key} 请求级白名单 "
                    f"{sorted(whitelist)} —— 禁止请求级覆盖受管 provider 配置"
                )
            merged[key] = value
    return _validate_options(options_key, merged)


def _provider_options_from_env(env: Mapping[str, str], model: str) -> dict[str, Any]:
    """环境变量分支（§7.1）：deepseek/ark-glm 模型 → registry defaults + LLM_* 覆盖。"""
    lower = model.lower()
    if lower.startswith("deepseek/"):
        merged = dict(DEFAULT_PROVIDER_OPTIONS.get("deepseek", {}))
        for key, env_key in (
            ("thinking", "LLM_THINKING"),
            ("reasoning_effort", "LLM_REASONING_EFFORT"),
        ):
            value = env.get(env_key, "")
            if value:
                merged[key] = value
        return _validate_options("deepseek", merged)
    if "glm" in lower:
        merged = dict(DEFAULT_PROVIDER_OPTIONS.get("ark-glm", {}))
        value = env.get("LLM_REASONING_EFFORT", "")
        if value:
            merged["reasoning_effort"] = value
        return _validate_options("ark-glm", merged)
    return {}


def _merge_probe_facts(profile: ModelProfile) -> ModelProfile:
    """probe 缓存事实合并（llm-capability-probe spec）：只读缓存，不发探测。

    命中 → merge_probe_into_profile 覆盖 capability（probe 为准）+
    probe_warnings，probe_required=False；未命中 → probe_required=True
    （消费方据此决定是否要求先探测）。解析期零真实 LLM 调用。
    """
    from finance_agent.llm.probe_cache import cache_key, get_probe_cache
    from finance_agent.llm.probes import merge_probe_into_profile

    report = get_probe_cache().get(
        cache_key(model=profile.model, base_url=profile.base_url, api_key=profile.api_key)
    )
    if report is None:
        return dataclasses.replace(profile, probe_required=True)
    return merge_probe_into_profile(profile, report)


def resolve_profile(
    *,
    purpose: Purpose = "deep",
    llm_config: dict[str, Any] | None = None,
    preset: str | None = None,
    _env: Mapping[str, str] | None = None,
) -> ModelProfile:
    """解析当前调用应使用的 ModelProfile（含 probe 缓存事实合并）。

    - preset：显式命名 preset（registry），优先于环境变量
    - llm_config：请求级配置（model/baseUrl/apiKey），必须完整
    - _env：环境映射注入（默认 os.environ），每次调用实时读取
    - probe 缓存命中 → capability 以 probe 事实为准；未命中 → probe_required
    """
    return _merge_probe_facts(
        _resolve_profile_static(purpose=purpose, llm_config=llm_config, preset=preset, _env=_env)
    )


def _resolve_profile_static(
    *,
    purpose: Purpose = "deep",
    llm_config: dict[str, Any] | None = None,
    preset: str | None = None,
    _env: Mapping[str, str] | None = None,
) -> ModelProfile:
    """静态解析（registry/env/request 三分支，不含 probe 合并）。"""
    env = _env if _env is not None else os.environ

    # 1. 请求级（必须原子完整）
    if llm_config:
        model = str(llm_config.get("model") or "")
        base_url = str(llm_config.get("baseUrl") or "") or None
        api_key = str(llm_config.get("apiKey") or "") or None
        api_form = llm_config.get("apiForm")
        if not model:
            raise IncompleteLLMConfigError("请求级 llm_config 缺 model")
        if not base_url:
            # 缺 baseUrl 才是半套；apiKey 可省（keyless 本地端点，如 Ollama），
            # 省略时显式 env 回退（LLM_API_KEY → DEEPSEEK_API_KEY），仍无则 None
            raise IncompleteLLMConfigError(
                f"请求级 llm_config 不完整（model={model}, baseUrl=缺）——"
                "缺端点才是半套配置；apiKey 可省略（env 回退或 keyless 端点）"
            )
        api_key = api_key or env.get("LLM_API_KEY", "") or env.get("DEEPSEEK_API_KEY", "") or None
        if api_form is not None and api_form not in _API_FORM_PROVIDER:
            raise IncompleteLLMConfigError(
                f"apiForm 必须为 chat_completion / messages / responses 之一，收到 {api_form!r}"
            )
        model = _ensure_prefix(model, base_url, api_form)
        provider = model.split("/", 1)[0]
        return ModelProfile(
            name=f"request:{model}",
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            capability=_PRESETS["openai-compatible"].capability,
            default_params={},
            api_form=api_form,
            provider_options=_provider_options_from_request(provider, llm_config),
        )

    # 2. 命名 preset
    if preset:
        return get_profile_preset(preset)

    # 3. 环境变量（按 purpose 分流；judge 独立映射，不回退 LLM_*）
    mapping = (
        _JUDGE_ENV
        if purpose == "judge"
        else (_LLM_QUICK_ENV if purpose == "quick" and env.get("LLM_QUICK_MODEL") else _LLM_ENV)
    )
    model, base_url, api_key = _resolve_from_env(env, mapping)
    if purpose == "judge" and not (model and base_url and api_key):
        # judge 环境缺任一关键字段：不静默借用 LLM_*，也不落 registry 默认
        # （显式失败好过打错网关——28 项全败的教训）
        raise IncompleteLLMConfigError(
            "judge 配置不完整（JUDGE_MODEL/JUDGE_BASE_URL/JUDGE_API_KEY），"
            "且不回退 LLM_* —— 请显式配置或显式选择 preset"
        )
    if not model:
        # 4. registry 默认
        return get_profile_preset("deepseek-official")
    if not base_url and not api_key:
        # 环境只有 model：按已知 provider 前缀走官方端点语义
        model = _ensure_prefix(model, None)
        base = (
            get_profile_preset("deepseek-official")
            if model.startswith("deepseek/")
            else get_profile_preset("openai-official")
        )
        return ModelProfile(
            name=f"env:{model}",
            provider=model.split("/", 1)[0],
            model=model,
            base_url=base_url,
            api_key=api_key,
            capability=base.capability,
            default_params={},
            provider_options=_provider_options_from_env(env, model),
        )
    if not base_url:
        # 有 apiKey 无端点仍是半套；有端点无 key 允许（keyless 本地端点）
        raise IncompleteLLMConfigError(
            f"环境变量配置不完整（model={model}, baseUrl=缺, apiKey={'有' if api_key else '缺'}）——"
            "缺端点才是半套配置；apiKey 可省略（keyless 端点）"
        )
    model = _ensure_prefix(model, base_url)
    cap = (
        _PRESETS["ark-glm"].capability
        if "glm" in model.lower()
        else _PRESETS["openai-compatible"].capability
    )
    return ModelProfile(
        name=f"env:{model}",
        provider=model.split("/", 1)[0],
        model=model,
        base_url=base_url,
        api_key=api_key,
        capability=cap,
        default_params={},
        provider_options=_provider_options_from_env(env, model),
    )
