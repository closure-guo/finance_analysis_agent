"""诊断：DeepSeek ReAct 工具调用是否泄漏 DSML 文本格式。

复现深度模式 `<｜｜DSML｜｜tool_calls>` 泄漏 bug：
- 直接调用 harness LiteLLMClient.chat_stream（与 ReAct Agent 同一条路径）
- 传入 search_stock 工具 + deep_mode system prompt + 用户输入"茅台"
- 观察输出是结构化 tool_calls 还是 DSML 原生文本标记

判定：
- 若 full_text 含 "DSML" / "｜｜" 且 tool_calls 为空 -> DSML 泄漏确认
- 若 tool_calls 非空 -> 工具调用被正确解析

Usage:
    python tests/scripts/diag_dsml_toolcall.py
    python tests/scripts/diag_dsml_toolcall.py "deepseek/deepseek-v4-pro"
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, "src")

from finance_agent.harness.litellm_client import LiteLLMClient  # noqa: E402
from finance_agent.prompts.loader import load_prompt  # noqa: E402

SEARCH_STOCK_TOOL = {
    "type": "function",
    "function": {
        "name": "search_stock",
        "description": (
            "根据自然语言查询搜索A股股票。当用户输入股票名称、行业描述、公司特征等模糊查询时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如股票名称、行业、公司特征等",
                },
            },
            "required": ["query"],
        },
    },
}


async def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
    print(f"模型        : {model}")
    print(f"API key     : {os.getenv('LLM_API_KEY', '')[:12]}...")
    print("=" * 70)

    client = LiteLLMClient(model=model)

    system_prompt = load_prompt("deep_mode").strip().format(now="2026-07-16 12:00")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "茅台"},
    ]

    full_text = ""
    tool_calls = None

    async for chunk in client.chat_stream(
        messages=messages,
        tools=[SEARCH_STOCK_TOOL],
        tool_choice="auto",
    ):
        if chunk.text_delta:
            full_text += chunk.text_delta
            print(f"[text_delta] {chunk.text_delta!r}")
        if chunk.tool_calls:
            tool_calls = chunk.tool_calls
            print(f"[tool_calls] {tool_calls}")
        if chunk.is_finished:
            print("[finished]")
            break

    print("=" * 70)
    print(f"完整文本 ({len(full_text)} chars):")
    print(full_text)
    print(f"\ntool_calls: {tool_calls}")

    has_dsml = "DSML" in full_text or "｜｜" in full_text or "invoke name" in full_text
    if has_dsml and not tool_calls:
        print("\n[!!] 确认 DSML 文本泄漏：工具调用以文本标记输出，未被解析为结构化 tool_calls")
    elif tool_calls:
        print("\n[OK] 工具调用被正确解析为结构化 tool_calls")
    else:
        print("\n[?] 无 DSML 也无 tool_calls，可能是纯文本回复（澄清反问）")


if __name__ == "__main__":
    asyncio.run(main())
