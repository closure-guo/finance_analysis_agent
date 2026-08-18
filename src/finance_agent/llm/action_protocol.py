# src/finance_agent/llm/action_protocol.py
"""ReAct action 文本协议兜底（delta Task 3.3，设计档案 §12）。

弱工具 provider（capability.tools == none）经本协议执行工具调用：
    <action name="search_stock">{"query":"茅台"}</action>
    → 执行结果以 <observation name="search_stock">...</observation> 回填
native tools 与 action 协议在 CanonicalToolCall 层归一，Agent 核心无感。
"""

from __future__ import annotations

import json
import re
from typing import Any

from finance_agent.harness.types import ToolCallRequest

_ACTION_RE = re.compile(r"<action\s+name=[\"']([^\"']+)[\"']\s*>(.*?)</action>", re.DOTALL)


def is_action_block(text: str) -> bool:
    return bool(_ACTION_RE.search(text or ""))


def extract_action(text: str) -> ToolCallRequest | None:
    """从 LLM 文本提取第一个 action；无 action 返回 None。

    参数按合法 JSON 解析；解析失败以 {"raw": ...} 兜底传递，
    由执行侧决定 repair 或拒绝（协议参数必须是 JSON）。
    """
    match = _ACTION_RE.search(text or "")
    if not match:
        return None
    name = match.group(1)
    raw_args = match.group(2).strip()
    try:
        arguments = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError:
        arguments = {"raw": raw_args}
    return ToolCallRequest(id=f"action:{name}", name=name, arguments=arguments)


def format_action(name: str, arguments: dict[str, Any]) -> str:
    """格式化 action 块（供 prompt 示例/测试 roundtrip）。"""
    return f'<action name="{name}">{json.dumps(arguments, ensure_ascii=False)}</action>'


def format_observation(name: str, content: str) -> str:
    """格式化 observation 回填块。"""
    return f'<observation name="{name}">{content}</observation>'
