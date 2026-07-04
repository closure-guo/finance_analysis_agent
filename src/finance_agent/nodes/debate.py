"""Layer II Bull/Bear 辩论 Agent。

每个辩论者：
1. 读取分析师报告和辩论历史
2. 调用 LLM 生成辩论消息
3. 返回 DebateMessage 列表（供 LangGraph reducer 追加）
"""

from __future__ import annotations

from finance_agent.llm import call_llm
from finance_agent.models import DebateMessage
from finance_agent.nodes._llm_utils import parse_json_response
from finance_agent.prompts.loader import load_prompt


def bull_debater(state: dict) -> dict:
    """Layer II Bull（看多）辩论者。"""
    context = _build_debate_context(state)
    system = load_prompt("bull_debater")
    api_key = state.get("api_key")

    response = call_llm(context, system=system, api_key=api_key)
    data = parse_json_response(response)
    msg = DebateMessage.model_validate(data)

    return {"debate_history": [msg]}


def bear_debater(state: dict) -> dict:
    """Layer II Bear（看空）辩论者。"""
    context = _build_debate_context(state)
    system = load_prompt("bear_debater")
    api_key = state.get("api_key")

    response = call_llm(context, system=system, api_key=api_key)
    data = parse_json_response(response)
    msg = DebateMessage.model_validate(data)

    return {"debate_history": [msg]}


def _build_debate_context(state: dict) -> str:
    """构建辩论的 LLM context。"""
    sections = []

    # 分析师报告摘要
    reports = state.get("analyst_reports") or {}
    for name, report in reports.items():
        if hasattr(report, "summary"):
            sections.append(f"[{name}] {report.summary}")
        elif isinstance(report, dict):
            sections.append(f"[{name}] {report.get('summary', '')}")

    # 辩论历史（第 2 轮需要参考第 1 轮）
    history = state.get("debate_history") or []
    if history:
        history_lines = []
        for msg in history:
            if hasattr(msg, "role"):
                history_lines.append(f"{msg.role}: {msg.content}")
            elif isinstance(msg, dict):
                history_lines.append(f"{msg.get('role', '?')}: {msg.get('content', '')}")
        sections.append("辩论历史:\n" + "\n".join(history_lines))

    return "\n\n".join(sections) if sections else "无可用数据"
