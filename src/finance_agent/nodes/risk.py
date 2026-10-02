"""Layer IV Risk Management — 风险辩论 Agent + Risk Judge。

3 个风险辩论者（aggressive/conservative/neutral）并行产出 DebateMessage，
Risk Judge 综合辩论给出最终 TradeDecision。
"""

from __future__ import annotations

import json
import logging
import math

from finance_agent.debate_anchors import anchor_stats, check_argument_anchors
from finance_agent.langfuse_tracing import update_current_span
from finance_agent.metrics.decision_price_check import check_decision_prices
from finance_agent.models import DebateMessage, TradeDecision
from finance_agent.nodes._llm_utils import call_llm_for_json, focus_hint
from finance_agent.nodes.validate import apply_payout_self_check as _apply_payout_self_check
from finance_agent.nodes.validate import final_price_missing, inaction_rationale_missing
from finance_agent.prompts.loader import load_prompt_with_meta

logger = logging.getLogger(__name__)


def _risk_debater(state: dict, role: str, prompt_name: str, node_name: str = "") -> dict:
    """风险辩论者通用逻辑。"""
    context = _build_risk_context(state)
    _pinfo = load_prompt_with_meta(prompt_name)
    system = _pinfo.template.replace("{role}", role)
    if role == "aggressive":
        system = system.replace("{perspective}", "激进收益")
    elif role == "conservative":
        system = system.replace("{perspective}", "保守风控")
    else:
        system = system.replace("{perspective}", "中性平衡")
    api_key = state.get("api_key")

    data = call_llm_for_json(
        context,
        system=system,
        api_key=api_key,
        node_name=node_name,
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
    )
    msg = DebateMessage.model_validate(data)

    # 论点锚点校验（add-debate-argument-anchors）：只落通道与 span stats，
    # fail-open 不改路由；resolved 仅表示锚存在，不代表锚支持论点
    checks = check_argument_anchors(msg, state)
    update_current_span(metadata={"anchor_stats": anchor_stats(checks)})

    return {"risk_debate_history": [msg], "debate_anchor_checks": checks}


def aggressive_debater(state: dict) -> dict:
    """Layer IV 激进型风险辩论者。"""
    return _risk_debater(state, "aggressive", "risk_debater", node_name="aggressive_debater")


def conservative_debater(state: dict) -> dict:
    """Layer IV 保守型风险辩论者。"""
    return _risk_debater(state, "conservative", "risk_debater", node_name="conservative_debater")


def neutral_debater(state: dict) -> dict:
    """Layer IV 中性型风险辩论者。"""
    return _risk_debater(state, "neutral", "risk_debater", node_name="neutral_debater")


def _recheck_price_note_after_retry(
    decision: TradeDecision, final_price_check: dict, cause: str
) -> None:
    """重试使终稿换代后复核价位结论（终审 I-1 模式）：如实改注，不再打回。

    cause 为重试回路名（「理由重试」/「再评估重试」），用于 note 措辞溯源。
    终稿换代为非执行动作时不得声称「价位齐备」（对 watch/hold 是错话）——
    双翻转终态措辞精确化（评审 Minor 收口）。
    """
    _price_after = final_price_missing(decision)
    if _price_after:
        final_price_check["note"] = (
            f"{cause}后终稿价位缺失：{'、'.join(_price_after)}（未再次打回，如实标注）"
        )
    elif final_price_check["note"]:
        # 双翻转终态措辞精确化（评审 Minor 收口）：终稿为非执行动作时不得声称
        # 「价位齐备」（对 watch/hold 是错话）——如实标注改为非执行动作。
        if str(getattr(decision, "action", "")) in ("watch", "hold"):
            final_price_check["note"] = (
                f"价位结论已被{cause}覆盖（终稿改为非执行动作，价位不适用，未再次打回）"
            )
        else:
            final_price_check["note"] = f"价位结论已被{cause}覆盖（终稿换代后价位齐备，未再次打回）"


def risk_judge(state: dict) -> dict:
    """Layer IV Risk Judge — 最终交易决策。"""
    context = _build_risk_context(state)
    _pinfo = load_prompt_with_meta("risk_judge")
    system = _pinfo.template
    api_key = state.get("api_key")

    data = call_llm_for_json(
        context,
        system=system,
        api_key=api_key,
        node_name="risk_judge",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
    )
    decision = TradeDecision.model_validate(data)
    # 终稿价位完整性（extend-payout-self-check-coverage，601888 实证：buy 价位全 None
    # 直通）：buy/sell 缺失首次打回重试一次；仍缺放行 + 如实标注（同 Trader 价检语义）
    final_price_check: dict = {"result": "pass", "note": ""}
    _missing = final_price_missing(decision)
    if _missing:
        retry_context = (
            f"{context}\n\n【价位完整性打回】{'buy' if decision.action == 'buy' else 'sell'}"
            f"决策必须结构化申报数值价位，缺失：{'、'.join(_missing)}。"
            "请重新输出补全 entry_price/stop_loss/target_price 的完整决策 JSON（继承或显式改写 Trader 价位均可，但必须以结构化字段申报）。"
        )
        data = call_llm_for_json(
            retry_context,
            system=system,
            api_key=api_key,
            node_name="risk_judge",
            llm_config=state.get("llm_config"),
            stock_code=state.get("stock_code"),
            prompt_name=_pinfo.prompt_name,
            prompt_version=_pinfo.prompt_version,
        )
        decision = TradeDecision.model_validate(data)
        _missing = final_price_missing(decision)
        if _missing:
            final_price_check["note"] = f"已打回仍未申报：{'、'.join(_missing)}"
        elif str(getattr(decision, "action", "")) in ("watch", "hold"):
            # 终审 I-1：重试输出非执行动作时「已申报」是错话——如实标注价位不适用
            final_price_check["note"] = "打回后改为非执行动作（价位不适用）"
        else:
            final_price_check["note"] = "打回后已申报"
    # 终稿非执行动作理由完整性（require-watch-hold-rationale）：watch/hold 缺理由
    # 首次打回重试一次；仍缺放行 + 如实标注（与 final_price_check 同款一次重试语义）
    final_inaction_check: dict = {"result": "pass", "note": ""}
    _missing_inaction = inaction_rationale_missing(decision)
    if _missing_inaction:
        retry_context = (
            f"{context}\n\n【非执行动作理由打回】watch/hold 终稿必须结构化申报不行动理由"
            f"与再评估触发条件，缺失：{'、'.join(_missing_inaction)}。"
            "请重新输出补全 inaction_reason（一句话，具体到当前不满足执行条件的点）与 "
            "reeval_triggers（1-3 条可观察、可判定的再评估触发条件）的完整决策 JSON。"
        )
        data = call_llm_for_json(
            retry_context,
            system=system,
            api_key=api_key,
            node_name="risk_judge",
            llm_config=state.get("llm_config"),
            stock_code=state.get("stock_code"),
            prompt_name=_pinfo.prompt_name,
            prompt_version=_pinfo.prompt_version,
        )
        decision = TradeDecision.model_validate(data)
        _missing_inaction = inaction_rationale_missing(decision)
        if _missing_inaction:
            final_inaction_check["note"] = f"已打回仍未申报：{'、'.join(_missing_inaction)}"
        else:
            final_inaction_check["note"] = "打回后已申报"
        # I-1（终审）：理由重试使终稿换代，价位块结论作废——复核并如实改注
        _recheck_price_note_after_retry(decision, final_price_check, "理由重试")
    # 终稿执行动作再评估触发条件必填化（update-decision-integrity-gates Task 3，
    # 601818 实证：sell 终稿无任何再评估触发条件，保守/中性方两轮辩论均点名
    # 「reeval_triggers 为空是纪律性缺陷」，FM 仍以「执行安排完备」批准）：buy/sell
    # 清洗后 reeval_triggers 为空 → 打回一次（与 final_price_check 同款一次重试语义），
    # feedback 提示可从风险辩论共识结构化申报；仍空放行 + 如实标注，MUST NOT 虚构
    # 条目。Trader 侧 plan 的 buy/sell 维持现状直通（缺口在终稿层收口，避免双点位
    # 校验叠加打回循环）。
    final_reeval_check: dict = {"result": "pass", "note": ""}
    if str(getattr(decision, "action", "")) in ("buy", "sell") and not decision.reeval_triggers:
        retry_context = (
            f"{context}\n\n【再评估触发条件打回】buy/sell 终稿必须结构化申报再评估触发条件"
            "（退出后监控机制），当前 reeval_triggers 为空，缺失：reeval_triggers。"
            "可从风险辩论中保守/中性方已提出的触发条件结构化申报"
            "（1-3 条可观察、可判定的再评估触发条件），"
            "请重新输出补全 reeval_triggers 的完整决策 JSON。"
        )
        data = call_llm_for_json(
            retry_context,
            system=system,
            api_key=api_key,
            node_name="risk_judge",
            llm_config=state.get("llm_config"),
            stock_code=state.get("stock_code"),
            prompt_name=_pinfo.prompt_name,
            prompt_version=_pinfo.prompt_version,
        )
        decision = TradeDecision.model_validate(data)
        if not decision.reeval_triggers:
            final_reeval_check["note"] = "已打回仍未申报再评估触发条件"
        else:
            final_reeval_check["note"] = "打回后已申报"
        # 重试使终稿换代，按既有「重试后复核前序结论」模式复核价位/理由结论
        # （不再触发新一轮打回，MUST NOT 死循环）
        _recheck_price_note_after_retry(decision, final_price_check, "再评估重试")
        _missing_inaction_after = inaction_rationale_missing(decision)
        if _missing_inaction_after:
            final_inaction_check["note"] = (
                "再评估重试后终稿改为非执行动作且理由缺失："
                f"{'、'.join(_missing_inaction_after)}（未再次打回，如实标注）"
            )
    # 赔率自检（任务 6 + extend-payout-self-check-coverage）：终稿 reasoning 自报赔率
    # vs 自身价位代码计算——冲突原位修正；转述窗口跳过（计数上报）
    _reasoning, _payout_fixed, _payout_skipped = _apply_payout_self_check(
        decision.reasoning,
        decision.action,
        decision.entry_price,
        decision.stop_loss,
        decision.target_price,
    )
    if _payout_fixed:
        decision = decision.model_copy(update={"reasoning": _reasoning})

    # 决策文本价位交叉校验门禁（update-decision-integrity-gates Task 1 →
    # update-decision-price-gate）：reeval_triggers/inaction_reason/reasoning 的
    # 自由文本价位 vs state 已验证技术指标。anomaly 非空 → 携明细定向打回重试一次 →
    # 重放 payout self-check → 复检；修正放行（note「打回后已修正」），仍异常 gate fail
    # （after_risk_judge 据此阻断，不进 FM 审批）。校验器自身异常 fail-open（放行 + 告警）。
    def _run_price_check(dec: TradeDecision) -> list[dict]:
        try:
            return check_decision_prices(
                dec,
                state.get("technical_indicators") or {},
                state.get("price_levels") or {},
                _latest_close_for_price_check(state),
            )
        except Exception:  # noqa: BLE001 -- fail-open：校验器自身异常不得阻断决策放行
            logger.warning("decision_price_check 执行失败（fail-open 放行）", exc_info=True)
            return []

    decision_price_anomalies = _run_price_check(decision)
    decision_price_gate: dict = {"result": "pass", "note": ""}
    if decision_price_anomalies:
        # 反馈四要素（delta spec）：原始文本片段（source_text）+ 指标名/已验证值/
        # 偏差幅度（message 携带）。单侧缺失退化为另一侧，两侧皆空不拼入；
        # 全部为空时兜底「（无明细）」，MUST NOT 拼出空反馈打回。
        feedback_parts: list[str] = []
        for anomaly in decision_price_anomalies:
            if not isinstance(anomaly, dict):
                continue
            sides = [str(anomaly.get("source_text") or ""), str(anomaly.get("message") or "")]
            detail = "：".join(part for part in sides if part)
            if detail:
                feedback_parts.append(detail)
        feedback = "；".join(feedback_parts) or "（无明细）"
        retry_context = (
            f"{context}\n\n【决策价位交叉校验打回】终稿自由文本价位与已验证技术指标冲突：{feedback}。"
            "请核对相关价位（以已验证指标值为准），修正后重新输出完整决策 JSON。"
        )
        data = call_llm_for_json(
            retry_context,
            system=system,
            api_key=api_key,
            node_name="risk_judge",
            llm_config=state.get("llm_config"),
            stock_code=state.get("stock_code"),
            prompt_name=_pinfo.prompt_name,
            prompt_version=_pinfo.prompt_version,
        )
        decision = TradeDecision.model_validate(data)
        decision_price_gate["note"] = "打回后已修正"
        # 重试换代重放 payout self-check（重试可能再引入自算赔率），计数合并不清零
        _reasoning2, _payout_fixed2, _payout_skipped2 = _apply_payout_self_check(
            decision.reasoning,
            decision.action,
            decision.entry_price,
            decision.stop_loss,
            decision.target_price,
        )
        if _payout_fixed2:
            decision = decision.model_copy(update={"reasoning": _reasoning2})
        _payout_fixed = _payout_fixed or _payout_fixed2
        _payout_skipped += _payout_skipped2
        # 重试换代复核价位完整性结论（I-1 模式：如实改注，不再打回，MUST NOT 死循环）
        _recheck_price_note_after_retry(decision, final_price_check, "价位交叉校验重试")
        # 重试换代复核兄弟结论（比照再评估重试 I-1 链，评审 Minor 收口）：终稿换代后
        # 理由/触发条件结论可能失真——如实改注，不再打回（MUST NOT 死循环、不得虚报「已申报」）
        _missing_inaction_after = inaction_rationale_missing(decision)
        if _missing_inaction_after:
            final_inaction_check["note"] = (
                "价位交叉校验重试后终稿为非执行动作且理由缺失："
                f"{'、'.join(_missing_inaction_after)}（未再次打回，如实标注）"
            )
        if not decision.reeval_triggers:
            final_reeval_check["note"] = (
                "价位交叉校验重试后终稿未申报再评估触发条件（未再次打回，如实标注）"
            )
        decision_price_anomalies = _run_price_check(decision)
        if decision_price_anomalies:
            decision_price_gate["result"] = "fail"
            decision_price_gate["note"] = f"已打回仍未通过：{len(decision_price_anomalies)} 条残留"

    return {
        "final_trade_decision": decision,
        "payout_ratio_corrected": _payout_fixed,
        "payout_ratio_conflict_skipped": _payout_skipped,
        "final_price_check": final_price_check,
        "final_inaction_check": final_inaction_check,
        "final_reeval_check": final_reeval_check,
        "decision_price_anomalies": decision_price_anomalies,
        "decision_price_gate": decision_price_gate,
    }


def _latest_close_for_price_check(state: dict) -> float | None:
    """最新收盘最稳取法：kline 尾行收盘（与 validate 同源）→ price_levels.entry_ref → None。

    形态噪声（空表/缺列/NaN/非数）一律回落下一级，取不到传 None——校验器据此
    跳过空洞检测、仅做偏差核对，MUST NOT 因行情缺位抛异常。
    """
    kline = state.get("kline")
    try:
        if kline is not None and len(kline) > 0:
            value = float(kline["收盘"].iloc[-1])
            if math.isfinite(value) and value > 0:
                return value
    except Exception:  # noqa: BLE001 -- 行情形态噪声回落 entry_ref，不阻断观测
        logger.debug(
            "latest_close 从 kline 尾行取值失败，回落 price_levels.entry_ref", exc_info=True
        )
    entry_ref = (state.get("price_levels") or {}).get("entry_ref")
    converted = float(entry_ref) if isinstance(entry_ref, (int, float)) else None
    if converted is not None and math.isfinite(converted) and converted > 0:
        return converted
    return None


def _build_risk_context(state: dict) -> str:
    """构建风险辩论的 LLM context。"""
    sections = []

    # 用户关注点（D5）：风险谱向用户期限/关注维度倾斜
    hint = focus_hint(state)
    if hint:
        sections.append(hint)

    # Trader 方案
    plan = state.get("trader_plan") or {}
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump()
    if isinstance(plan, dict) and plan:
        sections.append(f"交易方案: {json.dumps(plan, ensure_ascii=False)}")

    # 风控指标
    risk = state.get("risk_metrics") or {}
    if risk:
        sections.append(f"风控指标: {json.dumps(risk, ensure_ascii=False)}")

    # 派生指标（deterministic-derived-metrics）：validate 节点代码计算的
    # 止损距离/赔率随 context 下发，辩论方与裁决直接引用，不自行重算
    dm = state.get("derived_metrics") or {}
    if dm.get("stop_distance_pct") is not None and dm.get("risk_reward_ratio") is not None:
        sections.append(
            f"派生指标（代码计算）: 止损距离 {dm['stop_distance_pct']:.1%}、"
            f"赔率 {dm['risk_reward_ratio']:.2f}:1"
            "（算术已由代码完成，直接引用，MUST NOT 自行重算或改写）"
        )

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
