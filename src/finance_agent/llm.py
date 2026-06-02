"""litellm 薄封装 — 统一 LLM 调用接口。

环境变量：
- LLM_MODEL: 模型名（默认 deepseek/deepseek-v4-pro）
- LLM_API_KEY: API Key（默认读 Deepseek-Api-Key）
- LLM_BASE_URL: 可选，自定义 base URL（默认 https://api.deepseek.com）
- LLM_THINKING: 思考模式 enabled/disabled（默认 enabled）
- LLM_REASONING_EFFORT: 思考强度 low/high/max（默认 max）
"""

from __future__ import annotations

import os

import litellm

litellm.drop_params = True

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek/deepseek-v4-pro"


def call_llm(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
    api_key = os.environ.get("LLM_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))
    base_url = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL)
    thinking = os.environ.get("LLM_THINKING", "enabled")
    reasoning_effort = os.environ.get("LLM_REASONING_EFFORT", "max")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["api_base"] = base_url

    # DeepSeek 思考模式：不支持 temperature/top_p
    if thinking == "enabled":
        kwargs["reasoning_effort"] = reasoning_effort
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    else:
        kwargs["temperature"] = temperature

    resp = litellm.completion(**kwargs)
    return resp.choices[0].message.content
