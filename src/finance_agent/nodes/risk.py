"""Layer IV Risk Management — 风险辩论 Agent + Risk Judge。

3 个风险辩论者（aggressive/conservative/neutral）并行产出 DebateMessage，
Risk Judge 综合辩论给出最终 TradeDecision。
"""

from __future__ import annotations

import json

from finance_agent.models import DebateMessage, TradeDecision
from finance_agent.nodes._llm_utils import call_llm_streaming, parse_json_response
from finance_agent.prompts.loader import load_prompt


def _risk_debater(state: dict, role: str, prompt_name: str, node_name: str = "") -> dict:
    """风险辩论者通用逻辑。"""
    context = _build_risk_context(state)
    system = load_prompt(prompt_name).replace("{role}", role)
    if role == "aggressive":
        system = system.replace("{perspective}", "激进收益")
    elif role == "conservative":
        system = system.replace("{perspective}", "保守风控")
    else:
        system = system.replace("{perspective}", "中性平衡")
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name=node_name,
        llm_config=state.get("llm_config"),
    )
    data = parse_json_response(response)
    msg = DebateMessage.model_validate(data)

    return {"risk_debate_history": [msg]}


def aggressive_debater(state: dict) -> dict:
    """Layer IV 激进型风险辩论者。"""
    return _risk_debater(state, "aggressive", "risk_debater", node_name="aggressive_debater")


def conservative_debater(state: dict) -> dict:
    """Layer IV 保守型风险辩论者。"""
    return _risk_debater(state, "conservative", "risk_debater", node_name="conservative_debater")


def neutral_debater(state: dict) -> dict:
    """Layer IV 中性型风险辩论者。"""
    return _risk_debater(state, "neutral", "risk_debater", node_name="neutral_debater")


def risk_judge(state: dict) -> dict:
    """Layer IV Risk Judge — 最终交易决策。"""
    context = _build_risk_context(state)
    system = load_prompt("risk_judge")
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="risk_judge",
        llm_config=state.get("llm_config"),
    )
    data = parse_json_response(response)
    decision = TradeDecision.model_validate(data)

    return {"final_trade_decision": decision}


def _build_risk_context(state: dict) -> str:
    """构建风险辩论的 LLM context。"""
    sections = []

    # Trader 方案
    plan = state.get("trader_plan") or {}
    if isinstance(plan, dict):
        sections.append(f"交易方案: {json.dumps(plan, ensure_ascii=False)}")

    # 风控指标
    risk = state.get("risk_metrics") or {}
    if risk:
        sections.append(f"风控指标: {json.dumps(risk, ensure_ascii=False)}")

    # 风险辩论历史（第 2 轮参考第 1 轮）
    history = state.get("risk_debate_history") or []
    if history:
        history_lines = []
        for msg in history:
            if hasattr(msg, "content"):
                history_lines.append(f"{msg.role}: {msg.content}")
            elif isinstance(msg, dict):
                history_lines.append(f"{msg.get('role', '?')}: {msg.get('content', '')}")
        sections.append("风险辩论记录:\n" + "\n".join(history_lines))

    return "\n\n".join(sections) if sections else "无可用数据"
