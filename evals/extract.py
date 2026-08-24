# evals/extract.py
"""state → judge 变量提取(spec consistency/decision_grounding 变量映射)。

所有值截断到 4096 字节(truncate_for_trace 头尾保留),控制 judge prompt 体积。
state 缺失键一律给空字符串,judge 输入永不 KeyError。
"""

from __future__ import annotations

import json
import re
from typing import cast

from finance_agent.langfuse_tracing import truncate_for_trace

_JUDGE_MAX_BYTES = 4096
_CONCLUSION_HEADERS = ("结论", "总结", "交易建议")


def _trunc(text: str) -> str:
    return truncate_for_trace(text, _JUDGE_MAX_BYTES)


def extract_conclusion(report: str) -> str:
    """提取报告结论章节:行首 ## 结论/总结/交易建议 起,到下一 ## 或文末。

    找不到章节标题时取末尾 500 字符(design Open Question:首版启发式)。
    """
    if not report:
        return ""
    pattern = re.compile(
        r"^#{1,4}\s*(?:" + "|".join(_CONCLUSION_HEADERS) + r")[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(report)
    if match:
        return match.group(1).strip()
    return report[-500:]


def _as_dict(obj: object) -> dict:
    """state 元素可能是 dict 或 pydantic（LangGraph reducer 原样保留），统一转 dict。"""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return cast(dict, obj.model_dump())
    return {}


def _summarize_analyst_reports(reports: dict) -> str:
    parts: list[str] = []
    for name, rep in reports.items():
        rep = _as_dict(rep)
        if not rep:
            continue
        text = rep.get("summary") or rep.get("conclusion") or ""
        if not text:
            text = json.dumps(rep, ensure_ascii=False)[:500]
        claims = _format_claims(rep.get("claims") or [])
        if claims:
            text = f"{text}\n论据: {claims}"
        parts.append(f"【{name}】{text}")
    return "\n".join(parts)


def _format_claims(claims: list) -> str:
    """把报告 Claim 列表压缩成 judge 可核对的一行（论据 + 数值）。

    judge 需要具体数值核对 evidence_refs 的 claim（delta 根因 2：摘要
    抹掉数值导致「无中生有」误判）。interpretation 缺失时退回 stated_value。
    """
    items: list[str] = []
    for c in claims:
        c = _as_dict(c)
        if not c:
            continue
        interp = c.get("interpretation", "")
        value = c.get("stated_value", "")
        if interp and value not in ("", None):
            items.append(f"{interp}({value})")
        elif interp:
            items.append(interp)
        elif value not in ("", None):
            items.append(str(value))
    return "; ".join(items)


def _summarize_debate(history: list) -> str:
    parts: list[str] = []
    for msg in history:
        msg = _as_dict(msg)
        if not msg:
            continue
        role = msg.get("role", "?")
        content = msg.get("content", "")
        parts.append(f"【{role}】{content}")
    return "\n".join(parts)


def extract_judge_vars(state: dict, query: str = "") -> dict[str, str]:
    """提取 9 个 judge 变量,全字符串,缺失给 ""。"""
    report = state.get("final_report") or ""
    decision = state.get("final_trade_decision") or {}
    risk_debate = state.get("risk_debate_history") or []
    risk_tail = _summarize_debate(risk_debate[-2:]) if risk_debate else ""
    decision_txt = _serialize_decision(decision)
    return {
        "query": query,
        "report": _trunc(report),
        "report_conclusion": _trunc(extract_conclusion(report)),
        "analyst_reports": _trunc(_summarize_analyst_reports(state.get("analyst_reports") or {})),
        "debate_history": _trunc(_summarize_debate(state.get("debate_history") or [])),
        "research_manager_decision": _trunc(state.get("research_manager_conclusion") or ""),
        "trade_decision": _trunc(decision_txt),
        "risk_judgment": _trunc(decision_txt + ("\n" + risk_tail if risk_tail else "")),
        "fund_manager_decision": state.get("fund_manager_decision") or "",
    }


def _serialize_decision(decision: object) -> str:
    """把决策对象安全序列化为字符串。

    TradeDecision 为 pydantic 模型,json.dumps 直传会抛
    'Object of type TradeDecision is not JSON serializable'。
    pydantic 用 model_dump();dict 直传;其余 str() 兜底。
    """
    if not decision:
        return ""
    try:
        if hasattr(decision, "model_dump"):
            return json.dumps(decision.model_dump(), ensure_ascii=False)
        return json.dumps(decision, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(decision)
