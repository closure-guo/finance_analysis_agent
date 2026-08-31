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
import logging

from finance_agent.langfuse_tracing import truncate_for_trace, update_current_span
from finance_agent.models import AnalystReport
from finance_agent.nodes._llm_utils import call_llm_streaming, focus_hint, parse_json_response
from finance_agent.prompts.loader import load_prompt_with_meta

logger = logging.getLogger(__name__)

_VALID_CLAIM_TYPES = {
    "numerical",
    "temporal",
    "entity",
    "comparative",
    "regulatory",
    "computational",
}
_VALID_SOURCE_TYPES = {"data", "event", "llm_inference", "mixed"}


def _retry_feedback_section(state: dict, agent_name: str) -> str:
    """定向重试反馈段（harden-citation-semantic-coverage D3）：值级 FAIL 明细 +
    ground_truth 注入重试上下文——与旧「盲目重跑」的关键区别是给 LLM 改错信息。

    无反馈（首轮 / 非目标分析师 / feedback 缺该 agent 键）时返回 ""，使首轮
    与非目标分析师的 context 不受影响。"""
    feedback = (state.get("citation_retry_feedback") or {}).get(agent_name) or []
    if not feedback:
        return ""
    lines = ["## 上轮引用校验失败（必须修正以下数据引用，ground_truth 为真实值）"]
    for item in feedback:
        lines.append(
            f"- field_ref={item['field_ref']}：你写的值 {item['stated_value']}，"
            f"真实值 {item['ground_truth']}（偏差 {item['delta']}）。"
            f"原表述：{item['interpretation']}"
        )
    return "\n".join(lines)


def _sanitize_claims(data: dict, agent_name: str = "") -> dict:
    """修正 LLM 输出中非法的 claim 字段值。

    非法枚举值被强制改写为兜底值，并记录 WARNING —— 改写本身是有意的降级
    （保证管线不因单个 claim 失败中断），但需可观测，否则 prompt 与代码的
    枚举不一致会被系统性静默掩盖。
    """
    for claim in data.get("claims", []):
        claimType = claim.get("claim_type")
        if claimType not in _VALID_CLAIM_TYPES:
            logger.warning(
                "分析师 %s 的 claim_type 非法，已改写：%r -> 'entity'", agent_name, claimType
            )
            # 改写是刻意降级：保证管线不因单个 claim 失败中断，但需在 trace 可见
            update_current_span(
                metadata={
                    "degradation": "sanitize_claims",
                    "field": "claim_type",
                    "raw": claimType,
                    "fixed": "entity",
                },
                level="WARNING",
            )
            claim["claim_type"] = "entity"
        sourceType = claim.get("source_type")
        if sourceType not in _VALID_SOURCE_TYPES:
            logger.warning(
                "分析师 %s 的 source_type 非法，已改写：%r -> 'data'", agent_name, sourceType
            )
            update_current_span(
                metadata={
                    "degradation": "sanitize_claims",
                    "field": "source_type",
                    "raw": sourceType,
                    "fixed": "data",
                },
                level="WARNING",
            )
            claim["source_type"] = "data"
        # 必填字符串字段的 None 值兜底为空串
        for field in ("field_ref", "stated_value", "interpretation"):
            if claim.get(field) is None:
                claim[field] = ""
        # metric_name/period 为可选申报字段：非 None 时统一转 str（LLM 偶发
        # 把 period 输出成 int 2024），缺省保持 None（None = 未申报，校验跳过）。
        for field in ("metric_name", "period"):
            if claim.get(field) is not None:
                claim[field] = str(claim[field])
    return data


def _parse_analyst_report(response: str, agent_name: str) -> AnalystReport:
    """解析 LLM 响应为 AnalystReport，解析失败时降级为原始文本报告。

    降级保障单个分析师解析失败不拖垮整条管线，但会产出 claims=[]，
    而零 claim 使引用校验 all_passed=True（citation.py 的 failed == 0）。
    故降级 SHALL 记录 WARNING 并打标记，使问题可被发现而非静默通过。
    降级标记仅用于可观测性，不改变图的走向（不触发 citation retry，
    见 harden-llm-output-validation 决策 4 与 incidents/006）。
    """
    try:
        data = _sanitize_claims(parse_json_response(response), agent_name)
        return AnalystReport.model_validate(data)
    except Exception as e:
        logger.warning(
            "分析师 %s 的 LLM 输出解析失败，降级为原始文本报告：%s: %s",
            agent_name,
            type(e).__name__,
            e,
        )
        # 降级须在 trace 可见（此前完全静默），raw_excerpt 截断避免大文本进 span
        update_current_span(
            metadata={
                "degradation": "parse_degraded",
                "raw_excerpt": truncate_for_trace(response[:500]),
            },
            level="WARNING",
        )
        return AnalystReport(
            agent_name=agent_name,
            summary=response[:200] if response else "分析完成",
            key_findings=[],
            claims=[],
            markdown=response or "## 分析\n（LLM 响应解析失败，显示原始文本）",
            parse_degraded=True,
        )


def technical_analyst(state: dict) -> dict:
    """Layer I 技术面分析师 Agent。"""
    context = _build_technical_context(state)
    feedback = _retry_feedback_section(state, "technical")
    if feedback:
        context = f"{context}\n\n{feedback}"
    _pinfo = load_prompt_with_meta("technical_analyst")
    system = _pinfo.template
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="technical_analyst",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
    )
    report = _parse_analyst_report(response, "technical")

    return {"analyst_reports": {"technical": report}}


# analyst-context-budget delta：技术指标 context 窗口。250 期全窗口指标 JSON
# 使 technical_analyst 单次 LLM 调用 11.5~14 分钟（601700 深研事故）；60 期
# 足够覆盖 MA60/趋势/背离分析（macro_analyst 同理只取近 3 期）。
_TECHNICAL_CONTEXT_WINDOW = 60


def _trim_series(values: list, window: int) -> list:
    """序列裁剪到最近 window 期；不超过 window 期时原样返回。"""
    return values[-window:] if isinstance(values, list) and len(values) > window else values


def _trim_technical_indicators(
    indicators: dict, window: int = _TECHNICAL_CONTEXT_WINDOW
) -> tuple[dict, bool]:
    """各指标序列裁剪为最近 window 期，返回（裁剪后结构, 是否发生裁剪）。

    结构为 {指标组: {序列名: list}} 两层（MA/MACD/RSI/BOLL/KDJ 均如此），
    非常规形态原样保留（防御）。
    """
    trimmed_any = False
    out: dict = {}
    for group, series in indicators.items():
        if isinstance(series, dict):
            trimmed_group: dict = {}
            for key, values in series.items():
                new = _trim_series(values, window)
                trimmed_any = trimmed_any or (new is not values)
                trimmed_group[key] = new
            out[group] = trimmed_group
        else:
            new = _trim_series(series, window)
            trimmed_any = trimmed_any or (new is not series)
            out[group] = new
    return out, trimmed_any


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
        # analyst-context-budget（裁剪）+ fix-citation-contract-diseases（负索引）：
        # 序列裁剪到最近窗口期控制 token；负索引约定（-1=最新一期）使 LLM 引用与
        # 校验器解析按「长度无关」语义对齐，裁剪窗口此后怎么改都不影响校验。
        trimmed, did_trim = _trim_technical_indicators(indicators)
        # 数组方向声明（incident 022 第四类疾病）：序列为时间正序（旧→新），
        # 列表末尾为最新一期——LLM 按此读取 -1 语义，防止把展示首元素当最新。
        note = (
            f"各序列为最近 {_TECHNICAL_CONTEXT_WINDOW} 期，更早历史已省略；序列为时间正序（旧→新），列表末尾为最新一期；"
            if did_trim
            else "序列为时间正序（旧→新），列表末尾为最新一期；"
        )
        sections.append(
            "技术指标数据（state 键 technical_indicators；"
            f"{note}field_ref 引用序列值时用负索引：-1=最新一期）:\n"
            f"{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )

    return "\n\n".join(sections)


def macro_analyst(state: dict) -> dict:
    """Layer I 宏观分析师 Agent。"""
    context = _build_macro_context(state)
    feedback = _retry_feedback_section(state, "macro")
    if feedback:
        context = f"{context}\n\n{feedback}"
    _pinfo = load_prompt_with_meta("macro_analyst")
    system = _pinfo.template
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="macro_analyst",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
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
        # 只取最近 3 个月数据，减少 token 消耗；records 现挂在 "records" 键下（fetch 守卫结构）。
        trimmed = {}
        for key, value in macro.items():
            if isinstance(value, dict):
                recs = value.get("records") or []
                freshness = value.get("freshness")
                as_of = value.get("as_of_date")
                trimmed[key] = recs[:3]
                if freshness == "stale":
                    trimmed[f"{key} 数据滞后"] = (
                        f"最新至 {as_of or '未知日期'}，请按滞后数据处理并降级结论"
                    )
            else:
                trimmed[key] = value
        sections.append(
            f"宏观经济指标（state 键 macro_indicators，近3期）:\n"
            f"{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("宏观经济指标（state 键 macro_indicators）: 数据暂不可用")

    return "\n\n".join(sections)


def fundamental_analyst(state: dict) -> dict:
    """Layer I 基本面分析师 Agent。"""
    context = _build_fundamental_context(state)
    feedback = _retry_feedback_section(state, "fundamental")
    if feedback:
        context = f"{context}\n\n{feedback}"
    _pinfo = load_prompt_with_meta("fundamental_analyst")
    system = _pinfo.template
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="fundamental_analyst",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
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

    # 三大报表（近 3 年，减少 token）——财报降序（最新在前），head = 最新 3 年
    for name, key in [
        ("资产负债表", "balance_sheet"),
        ("利润表", "income_statement"),
        ("现金流量表", "cash_flow_statement"),
    ]:
        df = state.get(key)
        if df is not None and not df.empty:
            recent = df.head(3) if len(df) > 3 else df
            sections.append(f"{name}（state 键 {key}，近3年）:\n{recent.to_string(index=False)}")

    # 预计算指标（由降序财报计算，继承降序；head = 最新 3 年）
    indicators = state.get("financial_indicators")
    if indicators is not None and not indicators.empty:
        recent = indicators.head(3) if len(indicators) > 3 else indicators
        sections.append(
            f"预计算财务指标（state 键 financial_indicators）:\n{recent.to_string(index=False)}"
        )

    # 四维度指标
    for label, key in [
        ("盈利能力", "profitability_metrics"),
        ("偿债能力", "solvency_metrics"),
        ("运营效率", "efficiency_metrics"),
        ("现金流", "cashflow_metrics"),
    ]:
        val = state.get(key)
        if val:
            sections.append(
                f"{label}（state 键 {key}）:\n{json.dumps(val, ensure_ascii=False, default=str)}"
            )

    # 杜邦分析
    dupont = state.get("dupont_tree")
    if dupont:
        sections.append(
            f"杜邦分析（state 键 dupont_tree）:\n{json.dumps(dupont, ensure_ascii=False, default=str)}"
        )

    # 增长率
    growth = state.get("growth_rates")
    if growth:
        sections.append(
            f"增长率（state 键 growth_rates）:\n{json.dumps(growth, ensure_ascii=False, default=str)}"
        )

    # 红黄绿灯 + 异常
    lights = state.get("traffic_lights")
    if lights:
        sections.append(
            f"红黄绿灯（state 键 traffic_lights）:\n{json.dumps(lights, ensure_ascii=False, default=str)}"
        )
    anomalies = state.get("anomalies")
    if anomalies:
        sections.append(
            f"异常检测（state 键 anomalies）:\n{json.dumps(anomalies, ensure_ascii=False, default=str)}"
        )

    # 健康度
    health = state.get("health_score")
    if health:
        sections.append(
            f"健康度评分（state 键 health_score）:\n{json.dumps(health, ensure_ascii=False, default=str)}"
        )

    # 同业对比
    peer = state.get("peer_comparison")
    if peer:
        sections.append(
            f"同业对比（state 键 peer_comparison）:\n{json.dumps(peer, ensure_ascii=False, default=str)}"
        )

    # 相对估值
    rval = state.get("relative_valuation")
    if rval:
        sections.append(
            f"相对估值（state 键 relative_valuation）:\n{json.dumps(rval, ensure_ascii=False, default=str)}"
        )

    # GARP
    garp = state.get("garp_result")
    if garp:
        sections.append(
            f"GARP估值（state 键 garp_result）:\n{json.dumps(garp, ensure_ascii=False, default=str)}"
        )

    # 季度趋势
    qtrend = state.get("quarterly_trend")
    if qtrend:
        sections.append(
            f"季度趋势（state 键 quarterly_trend）:\n{json.dumps(qtrend, ensure_ascii=False, default=str)}"
        )

    return "\n\n".join(sections)


def sentiment_analyst(state: dict) -> dict:
    """Layer I 舆情分析师 Agent。"""
    context = _build_sentiment_context(state)
    feedback = _retry_feedback_section(state, "sentiment")
    if feedback:
        context = f"{context}\n\n{feedback}"
    _pinfo = load_prompt_with_meta("sentiment_analyst")
    system = _pinfo.template
    api_key = state.get("api_key")

    response = call_llm_streaming(
        context,
        system=system,
        api_key=api_key,
        node_name="sentiment_analyst",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
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
            f"新闻资讯（state 键 news_list，最近{len(trimmed)}条）:\n"
            f"{json.dumps(trimmed, ensure_ascii=False, default=str)}"
        )
    else:
        sections.append("新闻资讯（state 键 news_list）: 暂无数据")

    # 关键事件
    events = state.get("key_events") or []
    if events:
        sections.append(
            f"关键事件（state 键 key_events）:\n{json.dumps(events[:10], ensure_ascii=False, default=str)}"
        )

    return "\n\n".join(sections)
