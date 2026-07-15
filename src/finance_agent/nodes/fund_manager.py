"""Layer V Fund Manager Agent — 最终审批交易决策。"""

from __future__ import annotations

import json

from finance_agent.nodes._llm_utils import call_llm_streaming, focus_hint, parse_json_response
from finance_agent.prompts.loader import load_prompt


def fund_manager(state: dict) -> dict:
    """Layer V Fund Manager — 审批/拒绝/退回。"""
    context = _build_fund_manager_context(state)
    system = load_prompt("fund_manager")
    api_key = state.get("api_key")

    response = call_llm_streaming(context, system=system, api_key=api_key, node_name="fund_manager")
    data = parse_json_response(response)
    decision = data["decision"]

    result: dict = {"fund_manager_decision": decision}
    if decision == "return":
        result["return_count"] = state.get("return_count", 0) + 1

    return result


def _build_fund_manager_context(state: dict) -> str:
    """构建 Fund Manager 的 LLM context。"""
    sections = []

    # 用户关注点（来自深度研究意图澄清环节）
    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    # 最终交易决策
    decision = state.get("final_trade_decision") or {}
    if isinstance(decision, dict):
        sections.append(f"交易决策: {json.dumps(decision, ensure_ascii=False)}")

    # 风控指标
    risk = state.get("risk_metrics") or {}
    if risk:
        sections.append(f"风控指标: {json.dumps(risk, ensure_ascii=False)}")

    # 退回次数
    return_count = state.get("return_count", 0)
    sections.append(f"已退回次数: {return_count}（上限 1 次）")

    return "\n\n".join(sections)
