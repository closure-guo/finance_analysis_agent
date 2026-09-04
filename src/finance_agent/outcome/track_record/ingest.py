"""add-track-record Task 3 补丁:预测落库的共享入口(供 api 与 ReAct 深模式共用)。

背景:落库挂点原先只在旧 /api/analyze SSE 路径(api.py:1169);ADR-0017 统一后
深模式经 ReAct 的 run_deep_analysis 工具走 _stream_graph(agent_factory),
该路径无挂点 → 深度分析完成后 predictions 恒为 0(真实线上事故)。
本模块把「accumulated → predictions 全量记录」抽为中立函数,两条路径共用。
"""

from __future__ import annotations

import logging
from typing import Any

from finance_agent.outcome.track_record.model import insert_prediction

logger = logging.getLogger("finance_agent.track_record.ingest")


def persist_prediction_from_accumulated(
    accumulated: dict[str, Any], session_id: str, stock_code: str, stock_name: str
) -> None:
    """观点全量落 predictions(旁路:任何失败仅 ERROR,不阻断业务)。

    approve/reject/hold/watch 均记录;action→direction 映射(buy→long,
    sell→short,hold/watch→neutral);entry_price 取 quote 优先、kline 收盘兜底;
    缺入场价(quote 与 kline 均不可得)存档为 unresolvable(计入样本不计入胜率)。
    """
    try:
        decision = accumulated.get("final_trade_decision") or {}
        if not decision.get("action"):
            return
        action = decision["action"]
        direction = "long" if action == "buy" else ("short" if action == "sell" else "neutral")
        entry_price = (accumulated.get("stock_quote") or {}).get("price")
        if entry_price is None:
            kline = accumulated.get("kline")
            if kline is not None and len(kline) > 0:
                last = kline.iloc[-1] if hasattr(kline, "iloc") else kline[-1]
                entry_price = float(last["收盘"])
        status = "open"
        resolution_rule = None
        if entry_price is None:
            status = "unresolvable"
            resolution_rule = "missing_entry_price"
        symbol = f"{stock_code}.SH" if str(stock_code).startswith("6") else f"{stock_code}.SZ"
        insert_prediction(
            {
                "source_type": "live",
                "symbol": symbol,
                "symbol_name": stock_name,
                "direction": direction,
                "entry_price": float(entry_price) if entry_price is not None else None,
                "target_price": decision.get("target_price"),
                "confidence": decision.get("confidence"),
                "rationale_snapshot": {
                    "action": action,
                    "fund_manager_decision": accumulated.get("fund_manager_decision"),
                    "fund_manager_decision_reasoning": accumulated.get(
                        "fund_manager_decision_reasoning"
                    ),
                },
                "langfuse_trace_id": accumulated.get("langfuse_trace_id"),
                "timestamp": _now_iso(),
                "resolution_rule": resolution_rule,
            },
            status=status,
        )
        logger.info("prediction 已落库: %s %s status=%s", stock_code, action, status)
    except Exception:  # noqa: BLE001 - 旁路铁律:失败仅 ERROR 不阻断业务
        logger.exception("prediction 落库失败(不阻断业务)")


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat()
