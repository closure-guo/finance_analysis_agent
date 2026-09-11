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
# 结论性标题词表：兼容真实报告的编号式标题（「## 六、基金经理决策」）。
# 「多空辩论结论」是中间章节，标题命中时取最后一个（最终决策在报告末尾）。
_CONCLUSION_HEADERS = ("结论", "总结", "交易建议", "投资建议", "综合结论", "基金经理决策")
_CONCLUSION_TITLE_RE = re.compile(
    r"^#{1,4}\s*(?:[一二三四五六七八九十0-9]+[、.．]\s*)?"
    r"(?:结论|总结|交易建议|投资建议|综合结论|基金经理决策)[^\n]*\n"
    r"(.*?)(?=^#{1,4}\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _trunc(text: str) -> str:
    return truncate_for_trace(text, _JUDGE_MAX_BYTES)


def extract_conclusion(report: str) -> str:
    """提取报告结论章节：最后命中的结论性标题（含编号式「六、基金经理决策」）起，
    到下一标题或文末；无标题时从尾部最近断句边界起（避免从句子中间切出半句话）。"""
    if not report:
        return ""
    matches = list(_CONCLUSION_TITLE_RE.finditer(report))
    if matches:
        return matches[-1].group(1).strip()
    tail = report[-800:]
    # 无结论性标题时 fallback：优先段落边界（\n\n / 句号+换行），其次断句边界，
    # 避免从句子中间切出半句话
    for anchor, skip in (("\n\n", 2), ("。\n", 2)):
        idx = tail.rfind(anchor)
        if idx >= 0:
            return tail[idx + skip : idx + skip + 500].strip()
    idx = max(tail.rfind("。"), tail.rfind("；"))
    if idx >= 0:
        return tail[idx + 1 : idx + 501].strip()
    return tail[-500:].strip()


def _as_dict(obj: object) -> dict:
    """state 元素可能是 dict 或 pydantic（LangGraph reducer 原样保留），统一转 dict。"""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return cast(dict, obj.model_dump())
    return {}


def _summarize_analyst_reports(reports: dict) -> str:
    # 每 agent 展示上限（字节）：4 分析师并列时保证每个结论方向都可见——
    # 整体 head/tail 截断会把中间 agent 整段切掉（fundamental 不可见，
    # judge 的 consistency 评分与标注材料都拿不到各层结论，2026-09-09 回归）。
    # 4×_AGENT_MAX_BYTES ≈ 3200 < _JUDGE_MAX_BYTES(4096)，外层 _trunc 兜底不再命中。
    _AGENT_MAX_BYTES = 800

    parts: list[str] = []
    for name, rep in reports.items():
        rep = _as_dict(rep)
        if not rep:
            continue
        # add-agent-readable-conclusion：优先普通人可读结论（plain_conclusion），
        # 旧 trace 报告对象无该字段时回退 summary/conclusion（审计可读优先，黑话次要）
        text = rep.get("plain_conclusion") or rep.get("summary") or rep.get("conclusion") or ""
        if not text:
            text = json.dumps(rep, ensure_ascii=False)[:500]
        claims = _format_claims(rep.get("claims") or [])
        if claims:
            text = f"{text}\n论据: {claims}"
        parts.append(f"【{name}】{truncate_for_trace(text, _AGENT_MAX_BYTES)}")
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


def _rebuttal_coverage(history: list) -> str | None:
    """交锋覆盖率（D1 1.12）：各角色论点被对方回应的比例——零 token 确定性指标。

    覆盖率 = 被对方 rebuttal_to 引用的论点数（并集）/ 该角色论点总数。
    无 rebuttal_to 数据（历史 trace/首轮未开始）返回 None。
    """
    total: dict[str, int] = {}
    covered: dict[str, set] = {}
    prev_role: str | None = None
    prev_idx = -1
    prev_n_args = 0
    for idx, raw in enumerate(history):
        msg = _as_dict(raw)
        if not msg:
            continue
        role = str(msg.get("role", "?"))
        args = [str(a).strip() for a in (msg.get("key_arguments") or []) if str(a).strip()]
        rebuttal = msg.get("rebuttal_to") or []
        # 本条的 rebuttal_to 指向上一条发言（对方）的论点序号；被回应论点以
        # 「哪条发言的第几条」为键——序号在每条发言内从 1 重新计数，只按序号去重
        # 会把各轮的①合并，分子封顶在单轮论点数（r1 实证 8 条 trace 全「4/8」）
        if prev_role and rebuttal:
            covered.setdefault(prev_role, set()).update(
                (prev_idx, n) for n in rebuttal if isinstance(n, int) and 1 <= n <= prev_n_args
            )
        prev_role, prev_idx, prev_n_args = role, idx, len(args)
        total[role] = total.get(role, 0) + len(args)
    lines = []
    for role, cnt in total.items():
        if cnt == 0:
            continue
        lines.append(f"{role} 论点被回应 {len(covered.get(role, set()))}/{cnt}")
    return "；".join(lines) if lines else None


def _summarize_debate(history: list) -> str:
    # 每条发言上限（字节）：多轮【bull】【bear】交替时保证全部轮次可见——
    # 整体 head/tail 截断会把中间轮次连标签一起挖掉（judge 评「逐条交锋」时
    # 看不到交锋过程，2026-09-10 实测回归：2fd1ee6d 的【bear】标签被挖掉）。
    # 4 条发言 × 800 字节 ≈ 3200 < _JUDGE_MAX_BYTES(4096)，外层 _trunc 兜底不再命中。
    _MESSAGE_MAX_BYTES = 800
    # 论点行上限：key_arguments 是每轮立场骨架（LLM 已结构化输出），截正文时骨架
    # 必须全数在场——judge 的「逐条回应对方论点」以论点行为对照锚点。
    _ARGUMENTS_MAX_BYTES = 400

    parts: list[str] = []
    for msg in history:
        msg = _as_dict(msg)
        if not msg:
            continue
        role = msg.get("role", "?")
        content = msg.get("content", "")
        raw_args = msg.get("key_arguments") or []
        items = [str(a).strip() for a in raw_args if str(a).strip()]
        arg_line = ""
        if items:
            joined = "; ".join(items)
            if len(joined.encode("utf-8")) > _ARGUMENTS_MAX_BYTES:
                joined = joined.encode("utf-8")[:_ARGUMENTS_MAX_BYTES].decode(
                    "utf-8", errors="ignore"
                )
            arg_line = f"论点: {joined}\n"
        parts.append(f"【{role}】{arg_line}{truncate_for_trace(content, _MESSAGE_MAX_BYTES)}")
    # 交锋覆盖率尾行（确定性指标，1.12）：有 rebuttal_to 数据时才追加
    coverage = _rebuttal_coverage(history)
    if coverage:
        parts.append(f"交锋覆盖: {coverage}")
    return "\n".join(parts)


def _structured_report_var(state: dict) -> str:
    """deep 报告的 judge 变量 `report`：结构化拼装，替代全文 head/tail 截断。

    实证（4f58faf7）：final_report 约 2 万字符且开头为图表节——4096 字节挖心后
    judge 仅见图表路径与审批章，从章节标题幻觉推断「全面覆盖」恒 5 分。结构化
    拼装（聚焦/分析师/RM/交易方案/FM）保证可读分析内容在场；图片路径（judge
    无法读取的纯噪声）天然不进入。拼装为空时回退 final_report 全文（兼容）。
    """
    parts: list[str] = []
    focus_summary = state.get("focus_summary") or ""
    if focus_summary:
        parts.append(f"【研究聚焦】{focus_summary}")
    analyst = _summarize_analyst_reports(state.get("analyst_reports") or {})
    if analyst:
        parts.append(f"【分析师结论】{analyst}")
    rm = state.get("research_manager_conclusion") or ""
    if rm:
        parts.append(f"【研究经理结论】{rm}")
    trade = _serialize_decision(state.get("final_trade_decision") or state.get("trader_plan"))
    if trade:
        parts.append(f"【交易方案】{trade}")
    fm_decision = state.get("fund_manager_decision") or ""
    if fm_decision:
        fm_action = state.get("fund_manager_action")
        fm_conf = state.get("fund_manager_confidence")
        qualifier = ""
        if fm_action:
            qualifier = f"（操作定性 {fm_action}"
            if fm_conf is not None:
                qualifier += f"，置信度 {fm_conf}"
            qualifier += "）"
        fm_reasoning = (state.get("fund_manager_decision_reasoning") or "").strip()
        fm_text = f"{fm_decision}{qualifier}"
        if fm_reasoning:
            fm_text += f"\n理由: {fm_reasoning}"
        parts.append(f"【基金经理决策】{fm_text}")
    return "\n".join(parts)


def extract_judge_vars(state: dict, query: str = "") -> dict[str, str]:
    """提取 9 个 judge 变量,全字符串,缺失给 ""。"""
    raw_report = state.get("final_report") or ""
    report = _structured_report_var(state) or raw_report
    decision = state.get("final_trade_decision") or {}
    risk_debate = state.get("risk_debate_history") or []
    risk_tail = _summarize_debate(risk_debate[-2:]) if risk_debate else ""
    decision_txt = _serialize_decision(decision)
    # D1：FM 操作定性随决策进 judge 变量——「approve 批准的是什么方向」直接可见
    fm_decision = state.get("fund_manager_decision") or ""
    fm_action = state.get("fund_manager_action")
    fm_conf = state.get("fund_manager_confidence")
    fm_parts: list[str] = []
    if fm_decision:
        qualifier = ""
        if fm_action:
            qualifier = f"（操作定性 {fm_action}"
            if fm_conf is not None:
                qualifier += f"，置信度 {fm_conf}"
            qualifier += "）"
        fm_parts.append(f"{fm_decision}{qualifier}")
    fm_reasoning = state.get("fund_manager_decision_reasoning")
    if fm_reasoning:
        fm_parts.append(f"理由: {fm_reasoning}")
    return {
        "query": query,
        "report": _trunc(report),
        # D3：报告结论取「研究聚焦」分析综合（focus_summary），回退全文标题提取
        # （旧行为=审批章复述，与 FM 节点逐字重复，consistency 无独立信号）
        "report_conclusion": _trunc(state.get("focus_summary") or extract_conclusion(raw_report)),
        "analyst_reports": _trunc(_summarize_analyst_reports(state.get("analyst_reports") or {})),
        "debate_history": _trunc(_summarize_debate(state.get("debate_history") or [])),
        "research_manager_decision": _trunc(state.get("research_manager_conclusion") or ""),
        "trade_decision": _trunc(decision_txt),
        "risk_judgment": _trunc(decision_txt + ("\n" + risk_tail if risk_tail else "")),
        # #111：FM 理由随决策进 judge 变量（consistency 维度可见否决依据）
        "fund_manager_decision": "\n".join(fm_parts),
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
