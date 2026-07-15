"""Agent 节点共享的 LLM 工具函数。"""

from __future__ import annotations

import json
import re


def parse_json_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON，处理 markdown 代码块包裹和尾部多余文本。"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: extract first JSON object using raw_decode
    decoder = json.JSONDecoder()
    idx = text.find("{")
    if idx >= 0:
        obj, _ = decoder.raw_decode(text[idx:])
        return obj
    raise json.JSONDecodeError("No JSON object found", text, 0)


def focus_hint(state: dict) -> str:
    """从 state 提取用户关注点（深度研究意图澄清环节收集），返回 LLM context 注入行。

    focus 为空时返回空字符串，调用方据此决定是否 append。
    """
    focus = (state.get("focus") or "").strip()
    if not focus:
        return ""
    return f"用户关注点: {focus}"


def call_llm_streaming(
    prompt: str,
    system: str = "",
    api_key: str | None = None,
    node_name: str = "",
) -> str:
    """Like call_llm but streams thinking tokens via LangGraph custom stream writer.

    Uses call_llm_stream to get real LLM reasoning_content (thinking) and answer.
    Thinking tokens are forwarded to the LangGraph stream writer for real-time display.
    Returns the complete answer string (same interface as call_llm).
    """
    from finance_agent.llm import call_llm_stream

    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        writer = None

    answer_parts: list[str] = []
    for kind, text in call_llm_stream(prompt, system=system, api_key=api_key):
        if kind == "thinking" and writer:
            writer({"type": "thinking", "node": node_name, "token": text})
        elif kind == "answer":
            answer_parts.append(text)

    return "".join(answer_parts)
