"""Stub LLM 客户端--测试模式专用。

按固定节奏吐固定文本 delta，不返回 tool_call，确保 ReAct Agent 在 1 轮完成。
用于 E2E 门禁的确定性流式断言（见 openspec/changes/add-e2e-core-specs）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from finance_agent.harness.llm_client import LLMResponse

# 固定的 stub 响应文本（分块吐出）
_STUB_CHUNKS = [
    "这是",
    "一段",
    "测试用的",
    "固定回复。",
    "用于验证",
    "流式渲染",
    "的增量累积。",
]


class StubLLMClient:
    """测试模式 LLM 客户端，接口与 LiteLLMClient 一致。"""

    def __init__(self, model: str = "stub/test", api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.api_key = api_key or "stub-key"

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> AsyncIterator[LLMResponse]:
        """按固定节奏吐固定文本 delta，不返回 tool_call。"""
        for chunk in _STUB_CHUNKS:
            await asyncio.sleep(0.05)  # 控制节奏，让流式断言可观察
            yield LLMResponse(text_delta=chunk)
        yield LLMResponse(is_finished=True)

    def __repr__(self) -> str:
        return f"StubLLMClient(model={self.model})"
