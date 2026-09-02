"""离线回放：截断快照 → 完整编排 → TradeDecision → 复用 outcome.settle 结算。

结算语义（涨跌停递延/停牌顺延/跳空穿越/方向符号化）全部复用
outcome.settle.evaluate_decision，不另造一套（spec「绩效指标与基线对比」）。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from evals.ablation import build_variant_graph
from evals.backtest.data_snapshot import SnapshotResult, build_snapshot
from finance_agent.nodes.compute import compute_metrics
from finance_agent.outcome.settle import evaluate_decision


def build_decision_record(
    decision: dict, *, entry_price: float, decision_date: str, code: str
) -> dict:
    """TradeDecision 序列化 dict → evaluate_decision 契约的 decision record。

    entry_price 统一取决策日收盘（回测无实时盘口；结算从 T+1 行起评）。
    """
    return {
        "decision_id": f"backtest-{code}-{decision_date}",
        "action": decision.get("action", "hold"),
        "entry_price": float(entry_price),
        "stop_loss": decision.get("stop_loss"),
        "target_price": decision.get("target_price"),
        "timestamp": decision_date,
    }


def direction_agreement(actions: list[str]) -> float:
    """n 次重复的多数方向占比（spec：一致率 < 2/3 剔除或单独标注）。"""
    if not actions:
        return 0.0
    top = Counter(actions).most_common(1)[0][1]
    return top / len(actions)


def replay_decision(
    code: str,
    decision_date: str,
    *,
    snapshot: SnapshotResult | None = None,
    client: Any = None,
    full_kline: pd.DataFrame | None = None,
    full_benchmark: pd.DataFrame | None = None,
) -> dict:
    """单次回放：快照（截断）→ compute_metrics → 完整 5 层 → 结算（全量 K 线/基准）。"""
    snap = snapshot or build_snapshot(code, decision_date, client=client)
    state = {**snap.state}
    state.update(compute_metrics(state))  # type: ignore[arg-type]
    graph = build_variant_graph("full")
    final = graph.invoke({**state, "focus": f"{code} 综合评估投资价值"})
    # 编排 state 的 final_trade_decision 是 TradeDecision pydantic 对象
    # （[backtest-pilot] 缺陷修复：按 dict 用 .get 会 AttributeError）
    raw_decision = final.get("final_trade_decision")
    if raw_decision is not None and hasattr(raw_decision, "model_dump"):
        decision: dict = raw_decision.model_dump()
    else:
        decision = dict(raw_decision or {})
    kline: pd.DataFrame | None = full_kline if full_kline is not None else state.get("kline")
    entry_price = _close_on_or_before(kline, decision_date)
    raw_action = decision.get("action")
    # 口径统一：action 缺失记 "unknown"（与 replay_with_consistency 计数一致）
    action = str(raw_action or "unknown")
    # kline is None 运行时被 entry_price is None 覆盖,显式列出仅为类型收窄
    if entry_price is None or not raw_action or kline is None:
        return {
            "decision": decision,
            "settlement": None,
            "entry_price": None,
            "action": action,
            "decision_date": decision_date,
            "snapshot_metadata": snap.metadata,
            "final_report": final.get("final_report"),
        }
    record = build_decision_record(
        decision, entry_price=entry_price, decision_date=decision_date, code=code
    )
    benchmark = full_benchmark if full_benchmark is not None else state.get("benchmark_kline")
    settlement = evaluate_decision(record, kline, benchmark)
    return {
        "decision": decision,
        "settlement": settlement.__dict__ if settlement else None,
        "entry_price": entry_price,
        "action": action,
        "decision_date": decision_date,
        "snapshot_metadata": snap.metadata,
        "final_report": final.get("final_report"),
    }


def replay_with_consistency(
    code: str,
    decision_date: str,
    *,
    n: int = 3,
    snapshot: SnapshotResult | None = None,
    client: Any = None,
    full_kline: pd.DataFrame | None = None,
    full_benchmark: pd.DataFrame | None = None,
) -> dict:
    """同一快照重复回放 n 次：决策方向一致率 + 首次结算结果（一致性独立维度披露）。

    结算上下文（settlement/entry_price/action/decision_date）取首轮回放透传，
    供回测编排把单笔结算摊成持有期日收益（Task 10 _trade_daily_returns）。
    """
    snap = snapshot or build_snapshot(code, decision_date, client=client)
    actions: list[str] = []
    first: dict | None = None
    for _ in range(n):
        result = replay_decision(
            code, decision_date, snapshot=snap, full_kline=full_kline, full_benchmark=full_benchmark
        )
        # 口径统一：action 缺失记 "unknown"（与 replay_decision 返回一致）
        actions.append(str(result.get("action") or "unknown"))
        if first is None:
            first = result
    return {
        "code": code,
        "decision_date": decision_date,
        "actions": actions,
        "agreement": round(direction_agreement(actions), 4),
        "settlement": (first or {}).get("settlement"),
        "entry_price": (first or {}).get("entry_price"),
        "action": (first or {}).get("action"),
        "snapshot_metadata": snap.metadata,
    }


def _close_on_or_before(kline: pd.DataFrame | None, date: str) -> float | None:
    if kline is None or kline.empty:
        return None
    dates = kline["日期"].astype(str).str[:10]
    eligible = kline[dates <= date]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["收盘"])
