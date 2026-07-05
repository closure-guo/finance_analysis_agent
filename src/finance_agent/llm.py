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
) -> str:
    """Non-streaming LLM call — returns full response string."""
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
    # Quick mode also disables thinking for fast response
    disable_thinking = (
        messages is not None and any(m.get("role") == "tool" for m in messages)
    ) or quick

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
):
    """Non-streaming LLM call with tool support.

    Returns the full response object so caller can check ``tool_calls``.
    Always uses LLM_QUICK_MODEL and disables thinking mode.
    """
    model = os.environ.get("LLM_QUICK_MODEL", _QUICK_MODEL)

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
