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

import os

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

# ── Langfuse 可观测性 ───────────────────────────────────────────────
# 配置了 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 时，用自定义回调直接对接
# Langfuse SDK v4，绕过 litellm 内置 langfuse 集成的兼容性问题。
# 未配置时上方 no-op 补丁已禁用 litellm 内置集成，不影响本地运行。
if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
    import logging as _lf_log_mod

    _lf_logger = _lf_log_mod.getLogger("finance_agent.langfuse")
    _lf_logger.setLevel(_lf_log_mod.DEBUG)

    class _LangfuseCallback:
        """litellm 回调，将 LLM 调用上报到 Langfuse v4。"""

        def __init__(self):
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
            )

        def log_success_event(self, kwargs, completion_response, start_time, end_time):
            try:
                self._report(kwargs, completion_response, start_time, end_time)
            except Exception as e:
                _lf_logger.warning("Langfuse 上报失败: %s", e)

        def log_failure_event(self, kwargs, completion_response, start_time, end_time):
            try:
                self._report(kwargs, completion_response, start_time, end_time, error=True)
            except Exception as e:
                _lf_logger.warning("Langfuse 上报失败: %s", e)

        async def async_log_success_event(self, kwargs, completion_response, start_time, end_time):
            try:
                self._report(kwargs, completion_response, start_time, end_time)
            except Exception as e:
                _lf_logger.warning("Langfuse 上报失败: %s", e)

        async def async_log_failure_event(self, kwargs, completion_response, start_time, end_time):
            try:
                self._report(kwargs, completion_response, start_time, end_time, error=True)
            except Exception as e:
                _lf_logger.warning("Langfuse 上报失败: %s", e)

        def _report(self, kwargs, resp, start_time, end_time, error=False):
            model = kwargs.get("model", "unknown")
            messages = kwargs.get("messages", [])
            usage = getattr(getattr(resp, "usage", None), "model_dump", lambda: {})()
            output = {"error": str(resp)} if error else ""
            if not error:
                choices = getattr(resp, "choices", [])
                if choices:
                    output = getattr(choices[0].message, "content", "")

            self.client.start_observation(
                name=f"litellm:{model}",
                as_type="generation",
                input={"messages": messages},
                output=output,
                model=model,
                usage_details={
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                    "total": usage.get("total_tokens", 0),
                },
                completion_start_time=start_time,
            ).end()
            self.client.flush()

    try:
        _cb = _LangfuseCallback()
        litellm.success_callback.append(_cb)
        litellm.failure_callback.append(_cb)
    except Exception as e:
        _lf_logger.warning("Langfuse 初始化失败: %s", e, exc_info=True)

_DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
_QUICK_MODEL = "deepseek/deepseek-chat"


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
) -> dict:
    """Build litellm kwargs with provider-specific params."""
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    if stream:
        kwargs["stream"] = True

    key = _resolve_key(api_key)
    if key:
        kwargs["api_key"] = key

    base_url = os.environ.get("LLM_BASE_URL", "")
    if base_url:
        kwargs["api_base"] = base_url

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    # DeepSeek-specific: thinking mode
    is_ds = _is_deepseek(model)
    thinking = os.environ.get("LLM_THINKING", "enabled")

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
) -> str:
    """Non-streaming LLM call — returns full response string.

    If quick=True, uses LLM_QUICK_MODEL (default deepseek-chat) with thinking disabled.
    Use quick=True for simple tasks like JSON extraction, classification, etc.
    """
    if quick:
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
    )

    resp = litellm.completion(**kwargs)
    content = resp.choices[0].message.content
    # Fallback: if content is empty (thinking mode), use reasoning_content
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
):
    """Streaming LLM call — yields tokens one by one.

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for tool result follow-up calls).

    If ``quick=True``, uses LLM_QUICK_MODEL instead of LLM_MODEL.
    """
    if messages is not None or quick:
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
    )

    stream = litellm.completion(**kwargs)
    for chunk in stream:
        delta = chunk.choices[0].delta
        # Yield reasoning content (thinking) and answer content separately
        if delta and hasattr(delta, "reasoning_content") and delta.reasoning_content:
            yield ("thinking", str(delta.reasoning_content))
        if delta and delta.content:
            yield ("answer", str(delta.content))


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
):
    """Non-streaming LLM call with tool support.

    Returns the full response object so caller can check ``tool_calls``.
    Uses LLM_QUICK_MODEL by default; pass ``model`` to override (e.g. v4-pro for ReAct).

    If ``messages`` is provided, it replaces the default prompt/system construction
    (used for ReAct multi-turn dialogue with tool results).
    """
    if model is None:
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
    )
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    return litellm.completion(**kwargs)
