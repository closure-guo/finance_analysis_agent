"""ia_analyze: 投资分析 LLM 节点 — 双阶段生成 7 章 IA 报告。

Phase 1: 调 LLM 生成正文（第 3-6 章）
Phase 2: 基于正文调 LLM 生成执行摘要（第 2 章）
Phase 3: 用模板组装完整 7 章报告
"""

from __future__ import annotations

from datetime import datetime

from finance_agent.formatters import (
    format_growth_rates,
    format_risk_summary,
    format_stock_header,
    format_valuation_section,
)
from finance_agent.llm import call_llm
from finance_agent.prompts.loader import load_prompt, render_template


def ia_analyze(state: dict) -> dict:
    # ── 格式化 state 数据 → LLM context ──
    context = _build_context(state)

    # ── Phase 1: 生成正文（第 3-6 章）──
    system_prompt = load_prompt("ia_analyze")
    body_text = call_llm(context, system=system_prompt)

    # ── Phase 2: 生成执行摘要（第 2 章）──
    summary_prompt = load_prompt("ia_summary").replace("{{body}}", body_text)
    executive_summary = call_llm(summary_prompt, system="你是投资分析摘要撰写专家。", temperature=0.2)

    # ── Phase 3: 组装完整报告 ──
    report = _assemble_report(state, executive_summary, body_text)

    return {
        "investment_analysis": body_text,
        "investment_report": report,
    }


def _build_context(state: dict) -> str:
    sections = []

    header = format_stock_header(
        state.get("stock_quote") or {},
        state.get("industry_info") or {},
    )
    sections.append(header)

    valuation = format_valuation_section(
        state.get("relative_valuation"),
        state.get("garp_result"),
        state.get("stock_quote") or {},
    )
    sections.append(valuation)

    # 增长率与风险（复用 FA 的格式化器）
    growth = format_growth_rates(state.get("growth_rates") or {})
    sections.append(growth)

    risk = format_risk_summary(
        state.get("traffic_lights") or {},
        state.get("anomalies") or [],
    )
    sections.append(risk)

    # 同业对比标记
    peer = state.get("peer_comparison")
    if peer and peer.get("available"):
        sections.append("### 同业数据\n同业对比数据已可用，详见相对估值部分。")
    else:
        sections.append("### 同业数据\n无同业对比数据。")

    return "\n\n".join(sections)


def _assemble_report(state: dict, executive_summary: str, body_text: str) -> str:
    quote = state.get("stock_quote") or {}
    info = state.get("industry_info") or {}
    stock_name = quote.get("name") or info.get("name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    date = datetime.now().strftime("%Y-%m-%d")

    inc = state.get("income_statement")
    if inc is not None and not inc.empty:
        years = sorted(inc["报告日"].astype(str).tolist())
        data_range = f"{years[0][:4]}-{years[-1][:4]}"
    else:
        data_range = "N/A"

    return render_template(
        "investment_report",
        stock_name=stock_name,
        stock_code=stock_code,
        date=date,
        data_range=data_range,
        executive_summary=executive_summary,
        body=body_text,
    )
