"""@live 用例：真实 DeepSeek 链路，验证 reasoning / tool_calls 内容真实产生（防漂移）。

单测（mock）锁定的是埋点逻辑——Langfuse generation output 结构 {answer, reasoning,
tool_calls}、prompt 元数据挂载、降级不阻断；但「真实 LLM 是否真的下发
reasoning_content / tool_calls」只有真实调用能验证。本文件即 ADR-0015 要求的
@live 防漂移用例，nightly 跑，不进 PR 门禁（ci.yml -m "not live"）。

前置：DEEPSEEK_API_KEY 环境变量；无 key 时整文件 skip。
可选：LLM_LIVE_MODEL 覆盖模型名（默认 deepseek/deepseek-chat）。
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="需 DEEPSEEK_API_KEY"),
]

_LIVE_MODEL = os.getenv("LLM_LIVE_MODEL", "deepseek/deepseek-chat")


@pytest.mark.asyncio
async def test_live_reasoning_streamed_in_thinking_mode():
    """真实 DeepSeek thinking 模式：chat_stream 应 yield 非空 reasoning_delta。

    对应 spec「LLM Generation 推理内容可观测」：若 DeepSeek 停止下发
    reasoning_content（API 行为漂移），本用例失败，nightly 报警。
    """
    from finance_agent.harness.litellm_client import LiteLLMClient

    client = LiteLLMClient(model=_LIVE_MODEL, thinking="enabled", max_retries=1)

    reasoning_parts: list[str] = []
    text_parts: list[str] = []
    finished = False
    async for resp in client.chat_stream(
        messages=[{"role": "user", "content": "用一句话说明 ROE 的含义"}]
    ):
        if resp.reasoning_delta:
            reasoning_parts.append(resp.reasoning_delta)
        if resp.text_delta:
            text_parts.append(resp.text_delta)
        if resp.is_finished:
            finished = True

    assert finished, "流未正常结束（未收到 is_finished）"
    assert "".join(reasoning_parts), "thinking 模式未产生 reasoning_content（真实 API 行为漂移）"
    assert "".join(text_parts), "未产生最终回答 content"


def test_live_tool_calls_returned():
    """真实 DeepSeek tool calling：complete_with_tools 返回结构含 tool_calls。

    对应 spec「LLM Generation 工具调用决策可观测」：complete_with_tools 走
    非流式 litellm.completion，返回完整 response，tool_calls 在
    choices[0].message.tool_calls（migrate-off-legacy-llm-shim Task 3：
    原 call_llm_with_tools 直调 gateway.complete_with_tools）。
    """
    from finance_agent.llm.gateway import complete_with_tools

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_stock_price",
                "description": "查询 A 股最新价",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "股票代码，如 600519"}
                    },
                    "required": ["symbol"],
                },
            },
        }
    ]

    # 请求级 llm_config：复刻 legacy._request_config_dict 语义（baseUrl 回退 env）
    llm_config: dict = {"model": _LIVE_MODEL, "apiKey": os.environ["DEEPSEEK_API_KEY"]}
    if os.environ.get("LLM_BASE_URL"):
        llm_config["baseUrl"] = os.environ["LLM_BASE_URL"]

    resp = complete_with_tools(
        [{"role": "user", "content": "贵州茅台（600519）现在多少钱？请调用工具查询。"}],
        tools=tools,
        tool_choice="auto",
        llm_config=llm_config,
    )

    message = resp.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    assert tool_calls, "tool calling 未返回 tool_calls（真实 API 行为漂移）"
    names = [tc.function.name for tc in tool_calls]
    assert "get_stock_price" in names, f"未调用预期工具，实际: {names}"
