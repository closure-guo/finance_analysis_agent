"""Layer II Research Manager — 总结 Bull/Bear 辩论，给出研究结论。"""

from __future__ import annotations

from finance_agent.nodes._llm_utils import call_llm_streaming, focus_hint
from finance_agent.prompts.loader import load_prompt


def research_manager(state: dict) -> dict:
    """Layer II Research Manager - 输出纯文本结论。"""
    context = _build_research_context(state)
    system = load_prompt("research_manager")
    api_key = state.get("api_key")

    conclusion = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="research_manager",
        llm_config=state.get("llm_config"),
    )

    return {"research_manager_conclusion": conclusion}


def _build_research_context(state: dict) -> str:
    sections = []

    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    # 分析师报告摘要
    reports = state.get("analyst_reports") or {}
    for name, report in reports.items():
        if hasattr(report, "summary"):
            sections.append(f"[{name}] {report.summary}")
        elif isinstance(report, dict):
            sections.append(f"[{name}] {report.get('summary', '')}")

    # 辩论历史
    history = state.get("debate_history") or []
    if history:
        history_lines = []
        for msg in history:
            if hasattr(msg, "content"):
                history_lines.append(f"{msg.role}: {msg.content}")
            elif isinstance(msg, dict):
                history_lines.append(f"{msg.get('role', '?')}: {msg.get('content', '')}")
        sections.append("辩论记录:\n" + "\n".join(history_lines))

    return "\n\n".join(sections) if sections else "无可用数据"
