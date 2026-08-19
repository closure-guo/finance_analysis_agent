"""litellm 薄封装 — 统一 LLM 调用接口，支持多模型。

环境变量：
- LLM_MODEL: 深度模式模型名（默认 deepseek/deepseek-v4-pro）
- LLM_QUICK_MODEL: 快速模式模型名（默认 deepseek/deepseek-chat）
- LLM_API_KEY: API Key（兼容 DEEPSEEK_API_KEY 回退）
- LLM_BASE_URL: 可选，自定义 base URL（不设则由 litellm 按模型名路由）
- LLM_THINKING: DeepSeek 思考模式 enabled/disabled（默认 enabled，非 DeepSeek 自动忽略）
- LLM_REASONING_EFFORT: 思考强度 low/high/max（默认 max，仅 DeepSeek 生效）

支持的模型前缀（litellm 自动路由）：
- deepseek/*    → DeepSeek API
- openai/*      → OpenAI API
- anthropic/*   → Anthropic API
- gemini/*      → Google AI
- openai/xxx + LLM_BASE_URL → 任意 OpenAI 兼容端点（Ollama/vLLM 等）
"""

from __future__ import annotations

import contextlib
import os
import warnings
from dataclasses import dataclass
from typing import Any

import litellm

# litellm 运行时防护收口 adapter（delta add-llm-provider-gateway Task 1.4）：
# drop_params / disable_streaming_logging（incident 016 死锁防护）/
# litellm-langfuse 兼容补丁统一在 adapter 初始化设置，本模块不再各自配置。
from finance_agent.llm.adapters.litellm_adapter import ensure_litellm_runtime  # noqa: E402

ensure_litellm_runtime()

# ── Langfuse 可观测性（ADR-0015）───────────────────────────────────
# LLM 调用细节改由 start_as_current_observation 在 call_llm 三入口包裹，
# 自动挂到 CallbackHandler 已建好的图节点 span 下。
# 不再使用 _LangfuseCallback + start_observation（产生孤立 generation，无父子关系）。
from finance_agent.langfuse_tracing import get_langfuse as _get_langfuse  # noqa: E402
from finance_agent.langfuse_tracing import (  # noqa: E402
    open_span,
    truncate_for_trace,
)

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


def _is_deepseek(model: str) -> bool:
    """Check if model is a DeepSeek model."""
    return "deepseek" in model.lower()


def _resolve_key(api_key: str | None) -> str:
    """Resolve API key from explicit param or environment."""
    return api_key or os.environ.get("LLM_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))


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


def _build_kwargs(
    model: str,
    messages: list[dict],
    max_tokens: int,
    stream: bool = False,
    temperature: float = 0.3,
    api_key: str | None = None,
    tools: list[dict] | None = None,
    disable_thinking: bool = False,
    llm_config: LLMConfig | None = None,
) -> dict:
    """Build litellm kwargs with provider-specific params.

    配置解析优先级（请求级 llm_config → 环境变量 → 默认值）：
    - model: llm_config.model → 传入的 model 参数（已由调用方解析 quick/非 quick）
    - base_url: llm_config.baseUrl → LLM_BASE_URL → 空
    - api_key: llm_config.apiKey → api_key 参数 → LLM_API_KEY/DEEPSEEK_API_KEY
    - thinking: llm_config.thinking → LLM_THINKING → "enabled"
    """
    cfg = llm_config or LLMConfig()

    # model: llm_config.model 优先覆盖传入的 model 参数
    effectiveModel = cfg.model or model

    # 自动补 litellm provider 前缀：
    # 用户填了自定义 base_url（OpenAI 兼容端点）但模型名缺少 provider 前缀时，
    # litellm 无法识别调用协议（BadRequestError: LLM Provider NOT provided）。
    # 自定义 OpenAI 兼容端点统一用 openai/ 前缀路由。
    base_url = cfg.baseUrl or os.environ.get("LLM_BASE_URL", "")
    if base_url and effectiveModel and "/" not in effectiveModel:
        effectiveModel = f"openai/{effectiveModel}"

    kwargs: dict = {
        "model": effectiveModel,
        "messages": messages,
        # max_tokens 默认 16384（incident 016 遗留问题）：方舟 GLM-5.2 强制
        # thinking 且 reasoning 与正文共享 max_tokens 配额（实测简单问题
        # reasoning 即 ~2500 token），4096 会截断正文或令 content 为空。
        # 上限不影响计费（按实际用量），仅移动截断点。
        "max_tokens": max_tokens,
        # 整体请求超时（秒）：防 streaming 响应无限卡死（实测 GLM 端点
        # 偶发挂起 15min+ 冻结整个基线/管线）。thinking 模式慢，默认 300s，
        # LLM_TIMEOUT_SECONDS 可调；harness 路径 litellm_client 已有 120s。
        "timeout": float(os.environ.get("LLM_TIMEOUT_SECONDS", "300")),
    }

    if stream:
        kwargs["stream"] = True

    # api_key: llm_config.apiKey 优先于 api_key 参数，再回退环境变量
    effectiveKey = cfg.apiKey or api_key
    key = _resolve_key(effectiveKey)
    if key:
        kwargs["api_key"] = key

    # base_url: llm_config.baseUrl 优先于环境变量
    if base_url:
        kwargs["api_base"] = base_url

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    # DeepSeek-specific: thinking mode
    is_ds = _is_deepseek(effectiveModel)
    thinking = cfg.thinking or os.environ.get("LLM_THINKING", "enabled")

    if is_ds and thinking == "enabled" and not disable_thinking and not tools:
        # DeepSeek thinking mode: no temperature, use reasoning_effort
        # Note: thinking mode + tool calling not compatible, so skip when tools present
        kwargs["reasoning_effort"] = os.environ.get("LLM_REASONING_EFFORT", "max")
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    elif is_ds and tools:
        # Tool calling: explicitly disable thinking mode (v4-pro defaults to enabled)
        # Thinking mode does not support tool_choice parameter
        kwargs["temperature"] = temperature
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    else:
        # Standard mode: use temperature
        kwargs["temperature"] = temperature

    return kwargs


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
    if llm_config and llm_config.model:
        model = llm_config.model
    elif quick:
        model = os.environ.get("LLM_QUICK_MODEL", _QUICK_MODEL)
    else:
        model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = _build_kwargs(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
        disable_thinking=quick,
        llm_config=llm_config,
    )

    _lf = _get_langfuse()
    if _lf is not None:
        try:
            with _lf.start_as_current_observation(
                as_type="generation",
                name=agent or f"litellm:{model}",
                model=model,
                input={"messages": messages},
                metadata=_generation_metadata(
                    prompt_name, prompt_version, agent, session_id, stock_code
                ),
            ) as _gen:
                resp = litellm.completion(**kwargs)
                msg = resp.choices[0].message
                # reasoning_content 独立提取供 trace；content 缺失时 fallback 到 reasoning（保持旧行为）
                _reasoning_text = getattr(msg, "reasoning_content", "") or ""
                content = msg.content or ""
                if not content:
                    content = _reasoning_text
                _usage = getattr(resp, "usage", None)
                _ud = {}
                if _usage:
                    _ud = {
                        "input": getattr(_usage, "prompt_tokens", 0) or 0,
                        "output": getattr(_usage, "completion_tokens", 0) or 0,
                    }
                # output 结构化：answer + reasoning（裁剪防撑爆 Langfuse span）
                _gen.update(
                    output={
                        "answer": truncate_for_trace(str(content)),
                        "reasoning": truncate_for_trace(_reasoning_text),
                    },
                    usage_details=_ud,
                )
                return str(content)
        except Exception:
            _lf = None
    if _lf is None:
        resp = litellm.completion(**kwargs)
        content = resp.choices[0].message.content
        if not content:
            msg = resp.choices[0].message
            content = getattr(msg, "reasoning_content", "") or ""
        return str(content)


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


def call_llm_stream(
    prompt: str,
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


def _extract_with_tools_output(resp) -> dict:
    """从 litellm completion resp 提取结构化 generation output。

    返回 ``{answer, reasoning}``，非空 tool_calls 时追加 ``tool_calls`` 字段。
    供 ``call_llm_with_tools`` 的 Langfuse 主路径与降级路径共用，保证两路
    output 结构一致（reasoning 与 call_llm / chat_stream 对称；空 tool_calls
    省略 key，与 chat_stream 文本分支一致）。

    - answer: ``message.content``（缺失时为空串，不回退 reasoning —— 工具调用场景
      content 通常为空，回退会把 reasoning 当 answer 误导 trace）。
    - reasoning: ``message.reasoning_content`` 独立提取（DeepSeek thinking 模式）。
    - tool_calls: ``message.tool_calls`` 结构化为 ``[{name, arguments}]``，
      arguments 保留 LLM 原始 JSON 字符串并裁剪。
    """
    _message = None
    _choices = getattr(resp, "choices", [])
    if _choices:
        _message = getattr(_choices[0], "message", None)
    _output_text = (getattr(_message, "content", "") or "") if _message else ""
    _reasoning_text = (getattr(_message, "reasoning_content", "") or "") if _message else ""
    _output_tool_calls: list[dict] = []
    if _message is not None:
        _tc_list = getattr(_message, "tool_calls", None) or []
        for _tc in _tc_list:
            _func = getattr(_tc, "function", None)
            _tc_name = (getattr(_func, "name", "") or "") if _func else ""
            _tc_args = (getattr(_func, "arguments", "") or "") if _func else ""
            _output_tool_calls.append({"name": _tc_name, "arguments": truncate_for_trace(_tc_args)})
    out: dict = {
        "answer": truncate_for_trace(_output_text),
        "reasoning": truncate_for_trace(_reasoning_text),
    }
    if _output_tool_calls:
        out["tool_calls"] = _output_tool_calls
    return out


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

    Returns the full response object so caller can check ``tool_calls``.
    Uses LLM_QUICK_MODEL by default; pass ``model`` to override (e.g. v4-pro for ReAct).

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for ReAct multi-turn dialogue with tool results).

    llm_config.model（若提供）覆盖 model 参数的解析。

    prompt_name / prompt_version（ADR-0015 Task 4）：经 metadata 挂到 Langfuse
    generation，兑现「Prompt 元数据可追溯」。两者均 None 时不写 metadata 键。

    agent / session_id / stock_code：Langfuse generation 命名与过滤字段。
    agent 非空时 observation name 用 agent 名（而非 litellm:{model}）；
    三者仅在显式提供时写入 metadata（向后兼容）。
    """
    if llm_config and llm_config.model:
        model = llm_config.model
    elif model is None:
        model = os.environ.get("LLM_QUICK_MODEL", _QUICK_MODEL)

    if messages is None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    kwargs = _build_kwargs(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
        tools=tools,
        disable_thinking=True,
        llm_config=llm_config,
    )
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    _lf = _get_langfuse()
    if _lf is not None:
        try:
            with _lf.start_as_current_observation(
                as_type="generation",
                name=agent or f"litellm:{model}",
                model=model,
                input={"messages": messages},
                metadata=_generation_metadata(
                    prompt_name, prompt_version, agent, session_id, stock_code
                ),
            ) as _gen:
                resp = litellm.completion(**kwargs)
                _output_obj = _extract_with_tools_output(resp)
                _usage = getattr(resp, "usage", None)
                _ud = {}
                if _usage:
                    _ud = {
                        "input": getattr(_usage, "prompt_tokens", 0) or 0,
                        "output": getattr(_usage, "completion_tokens", 0) or 0,
                    }
                _gen.update(output=_output_obj, usage_details=_ud)
                return resp
        except Exception:
            _lf = None
    # 降级路径：start_as_current_observation 失败或未配置 Langfuse 时，
    # 经 open_span（自带 no-op 兜底）仍尝试记录 tool_calls/reasoning/answer，
    # 满足 spec「降级路径同样记录」；open_span 不可用时 yield None，业务不报错。
    with open_span(name=f"litellm:{model}", input={"messages": messages}) as _obs:
        resp = litellm.completion(**kwargs)
        if _obs is not None:
            with contextlib.suppress(Exception):  # trace 失败不影响业务
                _obs.update(output=_extract_with_tools_output(resp))
        return resp
