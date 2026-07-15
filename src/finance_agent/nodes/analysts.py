"""Layer I 分析师 Agent — 4 个并行分析师节点。

每个分析师：
1. 从 state 读取 PREP 数据
2. 构建 prompt context
3. 调用 LLM
4. 解析 JSON 响应为 AnalystReport
5. 返回 state 更新
"""

from __future__ import annotations

import json

from finance_agent.models import AnalystReport
from finance_agent.nodes._llm_utils import call_llm_streaming, focus_hint, parse_json_response
from finance_agent.prompts.loader import load_prompt

_VALID_CLAIM_TYPES = {
    "numerical",
    "temporal",
    "entity",
    "comparative",
    "regulatory",
    "computational",
}
_VALID_SOURCE_TYPES = {"data", "event", "llm_inference", "mixed"}


def _sanitize_claims(data: dict) -> dict:
    """Fix invalid claim values from LLM output."""
    for claim in data.get("claims", []):
        if claim.get("claim_type") not in _VALID_CLAIM_TYPES:
            claim["claim_type"] = "entity"
        if claim.get("source_type") not in _VALID_SOURCE_TYPES:
            claim["source_type"] = "data"
        # Fix None values in required string fields
        for field in ("field_ref", "stated_value", "interpretation"):
            if claim.get(field) is None:
                claim[field] = ""
    return data


def _parse_analyst_report(response: str, agent_name: str) -> AnalystReport:
    """Parse LLM response into AnalystReport, with fallback for malformed JSON."""
    try:
        data = _sanitize_claims(parse_json_response(response))
        return AnalystReport.model_validate(data)
    except Exception:
        # Fallback: construct minimal report from raw text
        return AnalystReport(
            agent_name=agent_name,
            summary=response[:200] if response else "分析完成",
            key_findings=[],
            claims=[],
            markdown=response or "## 分析\n（LLM 响应解析失败，显示原始文本）",
        )


def technical_analyst(state: dict) -> dict:
    """Layer I 技术面分析师 Agent。"""
    context = _build_technical_context(state)
    system = load_prompt("technical_analyst")
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context, system=system, api_key=api_key, node_name="technical_analyst"
    )
    report = _parse_analyst_report(response, "technical")

    return {"analyst_reports": {"technical": report}}


def _build_technical_context(state: dict) -> str:
    """构建技术面分析的 LLM context。"""
    sections = []

    stock_name = state.get("stock_name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    sections.append(f"股票: {stock_name}({stock_code})")

    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    indicators = state.get("technical_indicators") or {}
    if indicators:
        sections.append(f"技术指标数据:\n{json.dumps(indicators, ensure_ascii=False, default=str)}")

    return "\n\n".join(sections)


def macro_analyst(state: dict) -> dict:
    """Layer I 宏观分析师 Agent。"""
    context = _build_macro_context(state)
    system = load_prompt("macro_analyst")
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context, system=system, api_key=api_key, node_name="macro_analyst"
    )
    report = _parse_analyst_report(response, "macro")

    return {"analyst_reports": {"macro": report}}


def _build_macro_context(state: dict) -> str:
    """构建宏观分析的 LLM context。"""
    sections = []

    stock_name = state.get("stock_name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    industry = state.get("industry_info") or {}
    industry_name = industry.get("name", "N/A")
    sections.append(f"股票: {stock_name}({stock_code}), 所属行业: {industry_name}")

    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    macro = state.get("macro_indicators") or {}
    if macro:
        # 只取最近 3 个月数据，减少 token 消耗
        trimmed = {}
        for key, records in macro.items():
            if isinstance(records, list):
                trimmed[key] = records[-3:]
            else:
                trimmed[key] = records
        sections.append(
            f"宏观经济指标（近3期）:\n{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("宏观经济指标: 数据暂不可用")

    return "\n\n".join(sections)


def fundamental_analyst(state: dict) -> dict:
    """Layer I 基本面分析师 Agent。"""
    context = _build_fundamental_context(state)
    system = load_prompt("fundamental_analyst")
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context, system=system, api_key=api_key, node_name="fundamental_analyst"
    )
    report = _parse_analyst_report(response, "fundamental")

    return {"analyst_reports": {"fundamental": report}}


def _build_fundamental_context(state: dict) -> str:
    """构建基本面分析的 LLM context。"""
    sections = []

    stock_name = state.get("stock_name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    sections.append(f"股票: {stock_name}({stock_code})")

    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    # 三大报表（近 3 年，减少 token）
    for name, key in [
        ("资产负债表", "balance_sheet"),
        ("利润表", "income_statement"),
        ("现金流量表", "cash_flow_statement"),
    ]:
        df = state.get(key)
        if df is not None and not df.empty:
            recent = df.tail(3) if len(df) > 3 else df
            sections.append(f"{name}（近3年）:\n{recent.to_string(index=False)}")

    # 预计算指标
    indicators = state.get("financial_indicators")
    if indicators is not None and not indicators.empty:
        recent = indicators.tail(3) if len(indicators) > 3 else indicators
        sections.append(f"预计算财务指标:\n{recent.to_string(index=False)}")

    # 四维度指标
    for label, key in [
        ("盈利能力", "profitability_metrics"),
        ("偿债能力", "solvency_metrics"),
        ("运营效率", "efficiency_metrics"),
        ("现金流", "cashflow_metrics"),
    ]:
        val = state.get(key)
        if val:
            sections.append(f"{label}:\n{json.dumps(val, ensure_ascii=False, default=str)}")

    # 杜邦分析
    dupont = state.get("dupont_tree")
    if dupont:
        sections.append(f"杜邦分析:\n{json.dumps(dupont, ensure_ascii=False, default=str)}")

    # 增长率
    growth = state.get("growth_rates")
    if growth:
        sections.append(f"增长率:\n{json.dumps(growth, ensure_ascii=False, default=str)}")

    # 红黄绿灯 + 异常
    lights = state.get("traffic_lights")
    if lights:
        sections.append(f"红黄绿灯:\n{json.dumps(lights, ensure_ascii=False, default=str)}")
    anomalies = state.get("anomalies")
    if anomalies:
        sections.append(f"异常检测:\n{json.dumps(anomalies, ensure_ascii=False, default=str)}")

    # 健康度
    health = state.get("health_score")
    if health:
        sections.append(f"健康度评分:\n{json.dumps(health, ensure_ascii=False, default=str)}")

    # 同业对比
    peer = state.get("peer_comparison")
    if peer:
        sections.append(f"同业对比:\n{json.dumps(peer, ensure_ascii=False, default=str)}")

    # 相对估值
    rval = state.get("relative_valuation")
    if rval:
        sections.append(f"相对估值:\n{json.dumps(rval, ensure_ascii=False, default=str)}")

    # GARP
    garp = state.get("garp_result")
    if garp:
        sections.append(f"GARP估值:\n{json.dumps(garp, ensure_ascii=False, default=str)}")

    # 季度趋势
    qtrend = state.get("quarterly_trend")
    if qtrend:
        sections.append(f"季度趋势:\n{json.dumps(qtrend, ensure_ascii=False, default=str)}")

    return "\n\n".join(sections)


def sentiment_analyst(state: dict) -> dict:
    """Layer I 舆情分析师 Agent。"""
    context = _build_sentiment_context(state)
    system = load_prompt("sentiment_analyst")
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context, system=system, api_key=api_key, node_name="sentiment_analyst"
    )
    report = _parse_analyst_report(response, "sentiment")

    return {"analyst_reports": {"sentiment": report}}


def _build_sentiment_context(state: dict) -> str:
    """构建舆情分析的 LLM context。"""
    sections = []

    stock_name = state.get("stock_name", "N/A")
    stock_code = state.get("stock_code", "N/A")
    sections.append(f"股票: {stock_name}({stock_code})")

    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    # 新闻列表（取最近 15 条，减少 token）
    news = state.get("news_list") or []
    if news:
        recent_news = news[:15]
        # 只保留关键字段，减少 token
        trimmed = []
        for n in recent_news:
            trimmed.append(
                {
                    "title": n.get("title", ""),
                    "datetime": n.get("datetime", ""),
                    "source": n.get("source", ""),
                }
            )
        sections.append(
            f"新闻资讯（最近{len(trimmed)}条）:\n{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("新闻资讯: 暂无数据")

    # 关键事件
    events = state.get("key_events") or []
    if events:
        sections.append(f"关键事件:\n{json.dumps(events[:10], ensure_ascii=False, default=str)}")

    return "\n\n".join(sections)
