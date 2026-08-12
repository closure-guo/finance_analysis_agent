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
from dataclasses import dataclass

import litellm

litellm.drop_params = True

# ── Langfuse 兼容性修复 ─────────────────────────────────────────────
# litellm 1.85.x 与 langfuse 4.x 深度不兼容（version 属性、sdk_integration 参数、
# langfuse_sdk_version 属性等多处不匹配）。未配置 LANGFUSE key 时 litellm 仍会在
# function_setup / log_event 中尝试初始化，导致异常阻塞 LLM 调用。
# 此处补丁：添加 version 属性 + 把所有 Langfuse logger 方法变成空操作。
try:
    import importlib.metadata

    import langfuse

    if not hasattr(langfuse, "version"):
        _lf_ver = importlib.metadata.version("langfuse")
        langfuse.version = type("version", (), {"__version__": _lf_ver})()
except Exception:  # noqa: S110
    pass


def _lf_noop(self, *a, **kw):  # noqa: ARG001
    """空操作 — 替换 Langfuse logger 的所有方法。"""
    pass


def _lf_noop_init(self, *a, **kw):  # noqa: ARG001
    """空操作 __init__ — 设置必要属性避免其他方法报 AttributeError。"""
    self.langfuse_sdk_version = "4.13.0"
    self.Langfuse = None
    self.langfuse_client = None


for _cls_path in (
    "litellm.integrations.langfuse.langfuse.LangFuseLogger",
    "litellm.integrations.langfuse.langfuse_prompt_management.LangfusePromptManagement",
):
    try:
        _parts = _cls_path.rsplit(".", 1)
        _mod = __import__(_parts[0], fromlist=[_parts[1]])
        _cls = getattr(_mod, _parts[1])
        _cls.__init__ = _lf_noop_init
        for _method in ("log_event_on_langfuse", "_log_langfuse_v2", "_log_langfuse_v1"):
            if hasattr(_cls, _method):
                setattr(_cls, _method, _lf_noop)
    except Exception:  # noqa: S110
        pass

# ── Langfuse 可观测性（ADR-0015）───────────────────────────────────
# LLM 调用细节改由 start_as_current_observation 在 call_llm 三入口包裹，
# 自动挂到 CallbackHandler 已建好的图节点 span 下。
# 不再使用 _LangfuseCallback + start_observation（产生孤立 generation，无父子关系）。
from finance_agent.langfuse_tracing import get_langfuse as _get_langfuse  # noqa: E402
from finance_agent.langfuse_tracing import truncate_for_trace  # noqa: E402

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
        "max_tokens": max_tokens,
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
    max_tokens: int = 4096,
    api_key: str | None = None,
    quick: bool = False,
    llm_config: LLMConfig | None = None,
) -> str:
    """Non-streaming LLM call — returns full response string.

    If quick=True, uses LLM_QUICK_MODEL (default deepseek-chat) with thinking disabled.
    Use quick=True for simple tasks like JSON extraction, classification, etc.

    llm_config.model（若提供）覆盖 quick/非 quick 的 model 解析。
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
                name=f"litellm:{model}",
                model=model,
                input={"messages": messages},
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


def call_llm_stream(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    api_key: str | None = None,
    messages: list[dict] | None = None,
    quick: bool = False,
    llm_config: LLMConfig | None = None,
):
    """Streaming LLM call — yields tokens one by one.

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for tool result follow-up calls).

    If ``quick=True``, uses LLM_QUICK_MODEL instead of LLM_MODEL.

    llm_config.model（若提供）覆盖 quick/非 quick 的 model 解析。
    """
    if llm_config and llm_config.model:
        model = llm_config.model
    elif messages is not None or quick:
        model = os.environ.get("LLM_QUICK_MODEL", _QUICK_MODEL)
    else:
        model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)

    if messages is None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    # Tool result follow-up must disable thinking (DeepSeek requires reasoning_content passthrough)
    disable_thinking = messages is not None and any(m.get("role") == "tool" for m in messages)

    kwargs = _build_kwargs(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
        temperature=temperature,
        api_key=api_key,
        disable_thinking=disable_thinking,
        llm_config=llm_config,
    )

    _lf = _get_langfuse()
    _gen_cm = None
    _gen = None
    if _lf is not None:
        try:
            _gen_cm = _lf.start_as_current_observation(
                as_type="generation",
                name=f"litellm:{model}",
                model=model,
                input={"messages": messages},
            )
            _gen = _gen_cm.__enter__()
        except Exception:
            _gen = None
            _gen_cm = None

    try:
        _accumulated = ""
        _accumulated_reasoning_stream = ""  # 累加 DeepSeek reasoning_content（原生思考增量）
        _last_usage = None
        stream = litellm.completion(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta
            # Yield reasoning content (thinking) and answer content separately
            if delta and hasattr(delta, "reasoning_content") and delta.reasoning_content:
                _accumulated_reasoning_stream += str(delta.reasoning_content)
                yield ("thinking", str(delta.reasoning_content))
            if delta and delta.content:
                _accumulated += str(delta.content)
                yield ("answer", str(delta.content))
            _u = getattr(chunk, "usage", None)
            if _u:
                _last_usage = _u

        if _gen is not None:
            try:
                _ud = {}
                if _last_usage:
                    _ud = {
                        "input": getattr(_last_usage, "prompt_tokens", 0) or 0,
                        "output": getattr(_last_usage, "completion_tokens", 0) or 0,
                    }
                # output 结构化：answer + reasoning（裁剪防撑爆 Langfuse span）
                _gen.update(
                    output={
                        "answer": truncate_for_trace(_accumulated),
                        "reasoning": truncate_for_trace(_accumulated_reasoning_stream),
                    },
                    usage_details=_ud,
                )
                _gen.end()
            except Exception:  # noqa: S110
                pass
    finally:
        if _gen_cm is not None:
            with contextlib.suppress(Exception):
                _gen_cm.__exit__(None, None, None)


def call_llm_with_tools(
    prompt: str,
    system: str = "",
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    api_key: str | None = None,
    tool_choice: str = "auto",
    messages: list[dict] | None = None,
    model: str | None = None,
    llm_config: LLMConfig | None = None,
):
    """Non-streaming LLM call with tool support.

    Returns the full response object so caller can check ``tool_calls``.
    Uses LLM_QUICK_MODEL by default; pass ``model`` to override (e.g. v4-pro for ReAct).

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for ReAct multi-turn dialogue with tool results).

    llm_config.model（若提供）覆盖 model 参数的解析。
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
                name=f"litellm:{model}",
                model=model,
                input={"messages": messages},
            ) as _gen:
                resp = litellm.completion(**kwargs)
                _output = ""
                _choices = getattr(resp, "choices", [])
                if _choices:
                    _output = getattr(_choices[0].message, "content", "") or ""
                _usage = getattr(resp, "usage", None)
                _ud = {}
                if _usage:
                    _ud = {
                        "input": getattr(_usage, "prompt_tokens", 0) or 0,
                        "output": getattr(_usage, "completion_tokens", 0) or 0,
                    }
                _gen.update(output=str(_output), usage_details=_ud)
                return resp
        except Exception:
            _lf = None
    return litellm.completion(**kwargs)
