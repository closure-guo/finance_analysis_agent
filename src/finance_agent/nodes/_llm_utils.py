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
