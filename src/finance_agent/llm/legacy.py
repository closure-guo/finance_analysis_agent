"""legacy LLM 调用入口 — 5.1-C 起全部为 gateway 薄壳。

本模块不再直接 import litellm / Langfuse：所有请求构造、provider 选项、
错误归一与 Langfuse 观测收口在
``finance_agent.llm.gateway``（complete_text / complete_stream /
complete_with_tools / complete_stream_async）。旧公共 API
（call_llm / call_llm_stream / call_llm_with_tools / LLMConfig）保留签名
并触发 DeprecationWarning，既有 import 路径不变；新代码请直接用 gateway。

环境变量语义（由 resolver/registry 承接）：
- LLM_MODEL / LLM_QUICK_MODEL: 深度/快速模式模型名
- LLM_API_KEY（兼容 DEEPSEEK_API_KEY 回退）/ LLM_BASE_URL: 端点与凭据
- LLM_THINKING / LLM_REASONING_EFFORT: deepseek provider_options 覆盖
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from typing import Any

_DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
_QUICK_MODEL = "deepseek/deepseek-chat"


@dataclass
class LLMConfig:
    """请求级 LLM 配置，字段为 None 时回退环境变量。

    字段用 camelCase 命名（baseUrl / apiKey），与前端 JSON 契约及项目命名约定一致。
    """

    model: str | None = None
    baseUrl: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    apiKey: str | None = None  # noqa: N815  # camelCase 为前端 JSON 契约
    thinking: str | None = None


def _prompt_metadata(prompt_name: str | None, prompt_version: str | int | None) -> dict:
    """构造 generation metadata：仅在显式提供 prompt_name/version 时写入对应键。

    ADR-0015 Task 4：prompt 元数据可追溯。未传入时返回空 dict（与历史
    Langfuse 调用向后兼容，不污染 metadata 命名空间）。
    """
    md: dict = {}
    if prompt_name:
        md["prompt_name"] = prompt_name
    if prompt_version is not None:
        md["prompt_version"] = prompt_version
    return md


def _generation_metadata(
    prompt_name: str | None,
    prompt_version: str | int | None,
    agent: str = "",
    session_id: str | None = None,
    stock_code: str | None = None,
) -> dict:
    """构造 generation metadata：prompt 元数据 + agent/session/stock 过滤字段。

    agent/session_id/stock_code 仅在显式提供时写入（与 _prompt_metadata 相同的
    向后兼容约定，不污染 metadata 命名空间）。
    """
    md = _prompt_metadata(prompt_name, prompt_version)
    if agent:
        md["agent"] = agent
    if session_id:
        md["session_id"] = session_id
    if stock_code:
        md["stock_code"] = stock_code
    return md


def _request_config_dict(llm_config: Any, api_key: str | None) -> dict | None:
    """LLMConfig / dict → gateway 请求级 llm_config dict（5.1-B2 薄壳适配）。

    - 无 model → None（complete_stream 经 env/preset 解析）
    - baseUrl 缺 → env LLM_BASE_URL；apiKey 缺 → cfg.apiKey → api_key 参数
      → LLM_API_KEY → DEEPSEEK_API_KEY（镜像 legacy _build_kwargs 回退链）
    - thinking 仅在显式设置时携带
    """
    if isinstance(llm_config, LLMConfig):
        model = llm_config.model
        base_url = llm_config.baseUrl
        key = llm_config.apiKey
        thinking = llm_config.thinking
    elif isinstance(llm_config, dict):
        model = llm_config.get("model")
        base_url = llm_config.get("baseUrl")
        key = llm_config.get("apiKey")
        thinking = llm_config.get("thinking")
    else:
        return None
    if not model:
        return None
    cfg: dict = {"model": model}
    effective_base = base_url or os.environ.get("LLM_BASE_URL", "")
    if effective_base:
        cfg["baseUrl"] = effective_base
    effective_key = (
        key or api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    )
    if effective_key:
        cfg["apiKey"] = effective_key
    if thinking:
        cfg["thinking"] = thinking
    return cfg


# error 事件 finish_reason（类名字符串）→ errors 模块 typed error 类；
# 旧名别名（OutputTruncated 等）指向同一类，__name__ 归并无歧义。
from finance_agent.llm import errors as _llm_errors  # noqa: E402

_ERROR_CLASS_BY_NAME: dict[str, type] = {
    getattr(_llm_errors, _name).__name__: getattr(_llm_errors, _name)
    for _name in dir(_llm_errors)
    if isinstance(getattr(_llm_errors, _name), type)
    and issubclass(getattr(_llm_errors, _name), _llm_errors.LLMError)
}


def _llm_model_for_name(llm_config: Any, quick: bool) -> str:
    """observation 命名用 model 解析（镜像旧 litellm:{model} 行为）。"""
    cfg_model = None
    if isinstance(llm_config, LLMConfig):
        cfg_model = llm_config.model
    elif isinstance(llm_config, dict):
        cfg_model = llm_config.get("model")
    return (
        cfg_model or os.environ.get("LLM_QUICK_MODEL" if quick else "LLM_MODEL") or _DEFAULT_MODEL
    )


def call_llm(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 16384,
    api_key: str | None = None,
    quick: bool = False,
    llm_config: LLMConfig | None = None,
    prompt_name: str | None = None,
    prompt_version: str | int | None = None,
    agent: str = "",
    session_id: str | None = None,
    stock_code: str | None = None,
) -> str:
    """Non-streaming LLM call — returns full response string.

    .. deprecated:: 5.1-C
        薄壳转调 :func:`finance_agent.llm.gateway.complete_text`；观测收口在
        gateway（经 trace dict 传入），本函数不再直接触 litellm/Langfuse。

    If quick=True, uses LLM_QUICK_MODEL (default deepseek-chat) with thinking disabled.
    Use quick=True for simple tasks like JSON extraction, classification, etc.

    llm_config.model（若提供）覆盖 quick/非 quick 的 model 解析。

    prompt_name / prompt_version（ADR-0015 Task 4）：经 metadata 挂到 Langfuse
    generation，兑现「Prompt 元数据可追溯」。两者均 None 时不写 metadata 键
    （向后兼容）。

    agent / session_id / stock_code：Langfuse generation 命名与过滤字段。
    agent 非空时 observation name 用 agent 名（而非 litellm:{model}）；
    三者仅在显式提供时写入 metadata（向后兼容）。
    """
    warnings.warn(
        "call_llm 已弃用：请使用 finance_agent.llm.gateway.complete_text",
        DeprecationWarning,
        stacklevel=2,
    )
    from finance_agent.llm.types import Purpose

    purpose: Purpose = "quick" if quick else "deep"

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    cfg_dict = _request_config_dict(llm_config, api_key)
    trace = {
        "name": agent or f"litellm:{_llm_model_for_name(llm_config, quick)}",
        "metadata": _generation_metadata(
            prompt_name, prompt_version, agent, session_id, stock_code
        ),
    }

    from finance_agent.llm.gateway import complete_text

    text, meta = complete_text(
        messages,
        purpose=purpose,
        max_tokens=max_tokens,
        temperature=temperature,
        llm_config=cfg_dict,
        trace=trace,
    )
    # legacy 行为保留：content 为空时回退 reasoning_content
    if not text:
        text = meta.get("raw_reasoning") or ""
    return str(text)


def call_llm_stream(
    prompt: str = "",
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 16384,
    api_key: str | None = None,
    messages: list[dict] | None = None,
    quick: bool = False,
    llm_config: LLMConfig | None = None,
    prompt_name: str | None = None,
    prompt_version: str | int | None = None,
    agent: str = "",
    session_id: str | None = None,
    stock_code: str | None = None,
):
    """Streaming LLM call — yields ("thinking"/"answer", text) tuples.

    .. deprecated:: 5.1-B2
        薄壳转调 :func:`finance_agent.llm.gateway.complete_stream`；观测收口在
        gateway（经 trace dict 传入），本函数不再直接触 litellm/Langfuse。

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for tool result follow-up calls).

    llm_config 接受 LLMConfig 或完整 dict（model/baseUrl/apiKey[，thinking]）；
    缺 model 时由 gateway 经 env/preset 解析。

    agent / session_id / stock_code：Langfuse generation 命名与过滤字段（经
    trace metadata 透传给 gateway 观测）。
    """
    warnings.warn(
        "call_llm_stream 已弃用：请使用 finance_agent.llm.gateway.complete_stream",
        DeprecationWarning,
        stacklevel=2,
    )
    from finance_agent.llm.types import Purpose

    purpose: Purpose = "quick" if quick else "deep"

    if messages is None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    cfg_dict = _request_config_dict(llm_config, api_key)
    trace = {
        "name": agent or f"litellm:{_llm_model_for_name(llm_config, quick)}",
        "metadata": _generation_metadata(
            prompt_name, prompt_version, agent, session_id, stock_code
        ),
    }

    from finance_agent.llm.gateway import complete_stream

    for ev in complete_stream(
        messages,
        purpose=purpose,
        max_tokens=max_tokens,
        temperature=temperature,
        llm_config=cfg_dict,
        trace=trace,
    ):
        if ev.kind == "reasoning":
            yield ("thinking", ev.reasoning)
        elif ev.kind == "text":
            yield ("answer", ev.text)
        elif ev.kind == "error":
            err_cls = _ERROR_CLASS_BY_NAME.get(ev.finish_reason or "", _llm_errors.UnknownLLMError)
            raise err_cls(ev.raw.get("error") or ev.finish_reason or "LLM error")


def call_llm_with_tools(
    prompt: str,
    system: str = "",
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 16384,
    api_key: str | None = None,
    tool_choice: str = "auto",
    messages: list[dict] | None = None,
    model: str | None = None,
    llm_config: LLMConfig | None = None,
    prompt_name: str | None = None,
    prompt_version: str | int | None = None,
    agent: str = "",
    session_id: str | None = None,
    stock_code: str | None = None,
):
    """Non-streaming LLM call with tool support.

    .. deprecated:: 5.1-C
        薄壳转调 :func:`finance_agent.llm.gateway.complete_with_tools`；
        观测收口在 gateway（经 trace dict 传入），本函数不再直接触 litellm/Langfuse。

    Returns the full response object so caller can check ``tool_calls``.
    Uses LLM_QUICK_MODEL by default; pass ``model`` to override (e.g. v4-pro for ReAct).

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for ReAct multi-turn dialogue with tool results).

    llm_config.model（若提供）覆盖 model 参数的解析。

    计划内语义修正（5.1-C，零生产调用方）：deepseek thinking+tools 保持
    开启（registry provider_options 默认），不再显式 disabled；messages 的
    reasoning 回传由 sanitize_request_messages 按 capability 处理。

    prompt_name / prompt_version（ADR-0015 Task 4）：经 metadata 挂到 Langfuse
    generation，兑现「Prompt 元数据可追溯」。两者均 None 时不写 metadata 键。

    agent / session_id / stock_code：Langfuse generation 命名与过滤字段。
    agent 非空时 observation name 用 agent 名（而非 litellm:{model}）；
    三者仅在显式提供时写入 metadata（向后兼容）。
    """
    warnings.warn(
        "call_llm_with_tools 已弃用：请使用 finance_agent.llm.gateway.complete_with_tools",
        DeprecationWarning,
        stacklevel=2,
    )
    if messages is None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    # model 解析（legacy 优先级）：llm_config.model → model 参数 → LLM_QUICK_MODEL
    if llm_config and llm_config.model:
        cfg_dict = _request_config_dict(llm_config, api_key)
        model_for_name = llm_config.model
    elif model:
        cfg = _request_config_dict(LLMConfig(model=model), api_key) or {"model": model}
        if llm_config and llm_config.thinking:
            cfg["thinking"] = llm_config.thinking
        cfg_dict = cfg
        model_for_name = model
    else:
        cfg_dict = None
        model_for_name = os.environ.get("LLM_QUICK_MODEL", _QUICK_MODEL)

    trace = {
        "name": agent or f"litellm:{model_for_name}",
        "metadata": _generation_metadata(
            prompt_name, prompt_version, agent, session_id, stock_code
        ),
    }

    from finance_agent.llm.gateway import complete_with_tools

    return complete_with_tools(
        messages,
        tools=tools,
        tool_choice=tool_choice,
        purpose="quick",
        max_tokens=max_tokens,
        temperature=temperature,
        llm_config=cfg_dict,
        trace=trace,
    )
