"""Layer III Trader Agent — 基于分析师报告和辩论结论做出交易决策。"""

from __future__ import annotations

from finance_agent.models import TradeDecision
from finance_agent.nodes._llm_utils import call_llm_streaming, focus_hint, parse_json_response
from finance_agent.prompts.loader import load_prompt_with_meta


def trader(state: dict) -> dict:
    """Layer III Trader — 综合分析产出交易决策。"""
    context = _build_trader_context(state)
    _pinfo = load_prompt_with_meta("trader")
    system = _pinfo.template
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="trader",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
    )
    data = parse_json_response(response)
    decision = TradeDecision.model_validate(data)

    return {"trader_plan": decision}


def _build_trader_context(state: dict) -> str:
    """构建 Trader 的 LLM context。"""
    sections = []

    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    # 分析师报告
    reports = state.get("analyst_reports") or {}
    for name, report in reports.items():
        if hasattr(report, "summary"):
            sections.append(f"[{name}] {report.summary}")
        elif isinstance(report, dict):
            sections.append(f"[{name}] {report.get('summary', '')}")

    # 研究经理结论
    conclusion = state.get("research_manager_conclusion")
    if conclusion:
        sections.append(f"研究经理结论: {conclusion}")

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
