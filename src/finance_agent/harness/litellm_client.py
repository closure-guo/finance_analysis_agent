"""LiteLLM 适配的 LLM 客户端（CanonicalEvent→LLMResponse 翻译层）。

delta 5.1-C Task 4：chat_stream 收口 gateway.complete_stream_async，本模块
不再直接调用 litellm（无 _build_kwargs/自有重试/自有 Langfuse 观测），
仅做构造字段 → gateway 参数、CanonicalEvent → LLMResponse 的翻译。
provider 前缀补全 / provider options / 消息清洗 / 重试 / Langfuse 观测
分别归构造器、adapter 与 gateway。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from finance_agent.harness.llm_client import LLMResponse
from finance_agent.harness.types import ToolCallRequest

logger = logging.getLogger("finance_agent.harness.litellm_client")

# litellm 运行时防护收口 adapter（delta Task 1.4）：本模块可被独立导入
# （不经过 llm.py），经 adapter 幂等初始化保证 harness/quick 独立入口不漏防。
from finance_agent.llm.adapters.litellm_adapter import (  # noqa: E402
    ensure_litellm_runtime,
)

ensure_litellm_runtime()


def _resolve_key(api_key: str | None) -> str:
    """Resolve API key from explicit param or environment."""
    if api_key:
        return api_key
    env_key = os.environ.get("LLM_API_KEY", "")
    if env_key:
        return env_key
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _prompt_metadata(prompt_name: str | None, prompt_version: str | int | None) -> dict:
    """构造 generation metadata：仅在显式提供 prompt_name/version 时写入对应键。

    ADR-0015 Task 4：prompt 元数据可追溯。未传入时返回空 dict（与历史
    Langfuse 调用向后兼容）。
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
    agent: str | None = None,
) -> dict:
    """构造 generation metadata：prompt 元数据 + agent 过滤字段。

    agent 仅在显式提供时写入（与 _prompt_metadata 相同的向后兼容约定，
    不污染 metadata 命名空间）。
    """
    md = _prompt_metadata(prompt_name, prompt_version)
    if agent:
        md["agent"] = agent
    return md


class LiteLLMClient:
    """用 gateway 实现的 LLM 客户端，接口与 harness LLMClient 一致。"""

    def __init__(
        self,
        model: str = "deepseek/deepseek-chat",
        api_key: str | None = None,
        base_url: str | None = None,
        thinking: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        prompt_name: str | None = None,
        prompt_version: str | int | None = None,
        agent: str | None = None,
    ):
        self.model = model
        self.api_key = _resolve_key(api_key)
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "")

        # 自动补 litellm provider 前缀：
        # 用户填了自定义 base_url（OpenAI 兼容端点）但模型名缺少 provider 前缀时，
        # litellm 无法识别调用协议。自定义 OpenAI 兼容端点统一用 openai/ 前缀路由。
        if self.base_url and self.model and "/" not in self.model:
            self.model = f"openai/{self.model}"
        self.thinking = thinking
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        self.agent = agent

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> AsyncIterator[LLMResponse]:
        """流式聊天请求：包装 gateway.complete_stream_async，翻译 CanonicalEvent。"""
        from finance_agent.llm.gateway import complete_stream_async

        # 请求级配置：model/baseUrl/apiKey 三者齐备才原子下发，
        # 否则 None 交给 resolver 用 env/preset（与 legacy._request_config_dict 语义一致）。
        llm_config: dict[str, Any] | None = None
        if self.model and self.base_url and self.api_key:
            llm_config = {"model": self.model, "baseUrl": self.base_url, "apiKey": self.api_key}

        trace = {
            "name": self.agent or f"litellm:{self.model}",
            "metadata": _generation_metadata(self.prompt_name, self.prompt_version, self.agent),
        }

        finished_yielded = False
        _gen = complete_stream_async(
            messages,
            purpose="react",
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            llm_config=llm_config,
            trace=trace,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            # 输出预算保真：harness 为 legacy 生产 ReAct 路径，输出预算固定 16384
            # （incident-016 类：reasoning 与正文共享配额，8192 会截断 deep 输出）。
            # 请求级配置解析时 resolver 会强制 openai-compatible preset（max_output=8192），
            # 此处显式下发 16384 以精确复刻旧 _build_kwargs 合同，不改 resolver 能力选择。
            max_tokens=16384,
        )
        try:
            async for ev in _gen:
                if ev.kind == "reasoning":
                    yield LLMResponse(reasoning_delta=ev.reasoning)
                elif ev.kind == "text":
                    yield LLMResponse(text_delta=ev.text)
                elif ev.kind == "tool_call":
                    calls: list[ToolCallRequest] = []
                    for i, tc in enumerate((ev.tool_call or {}).get("calls", [])):
                        raw_args = tc.get("function", {}).get("arguments", "")
                        try:
                            args = json.loads(raw_args) if raw_args else {}
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(
                                "tool_call arguments 非法 JSON，降级空 dict: %s", raw_args
                            )
                            args = {}
                        calls.append(
                            ToolCallRequest(
                                id=tc.get("id") or f"call_{i}",
                                name=tc.get("function", {}).get("name", ""),
                                arguments=args,
                            )
                        )
                    yield LLMResponse(tool_calls=calls, is_finished=True)
                    finished_yielded = True
                elif ev.kind == "finished":
                    if not finished_yielded:
                        yield LLMResponse(is_finished=True)
                    return
        finally:
            # finished 后生成器仍悬挂在 yield 点：显式 aclose 使 gateway 的观测收尾
            # （Langfuse CM __exit__）在本任务上下文执行。留给 GC 跨上下文 aclose
            # 会触发 OTel "token created in a different Context" detach 告警。
            with contextlib.suppress(Exception):
                await _gen.aclose()

    def __repr__(self) -> str:
        return f"LiteLLMClient(model={self.model})"
