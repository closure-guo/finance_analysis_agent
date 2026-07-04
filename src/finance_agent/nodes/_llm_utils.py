"""Agent 节点共享的 LLM 工具函数。"""

from __future__ import annotations

import json
import re


def parse_json_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON，处理 markdown 代码块包裹。"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return json.loads(text)
