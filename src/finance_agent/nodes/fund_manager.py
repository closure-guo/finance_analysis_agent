"""Layer V Fund Manager Agent — 最终审批交易决策。"""

from __future__ import annotations

import json
import logging

from finance_agent.langfuse_tracing import get_langfuse
from finance_agent.models import FundManagerDecision
from finance_agent.nodes._llm_utils import call_llm_for_json, focus_hint
from finance_agent.prompts.loader import load_prompt_with_meta

logger = logging.getLogger("finance_agent.fund_manager")


def fund_manager(state: dict) -> dict:
    """Layer V Fund Manager — 审批/拒绝/退回。"""
    context = _build_fund_manager_context(state)
    _pinfo = load_prompt_with_meta("fund_manager")
    system = _pinfo.template
    api_key = state.get("api_key")

    data = call_llm_for_json(
        context,
        system=system,
        api_key=api_key,
        node_name="fund_manager",
        llm_config=state.get("llm_config"),
        stock_code=state.get("stock_code"),
        prompt_name=_pinfo.prompt_name,
        prompt_version=_pinfo.prompt_version,
    )
    # 枚举强校验：非法值/缺键抛 ValidationError 中断管线，不静默降级为 approve
    # （加固前为 data["decision"] 裸取键，非法值经 routing 的 else 分支被当作批准放行）
    decision = FundManagerDecision.model_validate(data).decision

    result: dict = {"fund_manager_decision": decision}
    if decision == "return":
        result["return_count"] = state.get("return_count", 0) + 1
    if decision == "approve":
        # 决策落库需要 trace 关联:节点内 OTel 上下文可用(citation_node 同款 get_langfuse 模式)
        try:
            client = get_langfuse()
            trace_id = client.get_current_trace_id() if client else None
            if trace_id:
                result["langfuse_trace_id"] = trace_id
        except Exception:
            logger.warning("trace_id 捕获失败,decision_log 将无 trace 关联", exc_info=True)

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
