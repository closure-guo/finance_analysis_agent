"""结算纯函数(design 决策 2/3/4/5)。全部合成 DataFrame 可测,不调 LLM/网络。

结算优先级:止损 > 目标 > 超期(expired);同日触及两者按止损(保守)。
一字板(open==high==low==close)触及 → 递延至打开首日开盘价,hold_days 含等待日。
停牌无 K 线行 → 行驱动迭代自然顺延,hold_days 只数有数据的交易日。
评估起点:decision_date 之后的行(T+1 起评)。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

MAX_HOLD_DAYS = int(os.getenv("MAX_HOLD_DAYS", "20"))
STALE_DAYS = int(os.getenv("DECISION_STALE_DAYS", "5"))
BENCHMARK_CODE = os.getenv("BENCHMARK_CODE", "000300")


@dataclass
class Settlement:
    status: str  # hit_stop / hit_target / expired
    settle_date: str
    settle_price: float
    hold_days: int
    decision_return: float
    benchmark_return: float | None
    decision_excess: float | None
    decision_hit: bool


def _direction_sign(action: str) -> float:
    """buy 为正;sell/hold/watch 取负(建议不买/卖出后下跌为正)。"""
    return 1.0 if action == "buy" else -1.0


def _is_one_word_board(row: pd.Series) -> bool:
    """一字板:开=高=低=收(全天未打开)。"""
    return row["开盘"] == row["最高"] == row["最低"] == row["收盘"]


def _bench_close_on_or_before(benchmark: pd.DataFrame, date: str) -> float | None:
    """基准在 date 或之前最后一个收盘。"""
    eligible = benchmark[benchmark["日期"] <= date]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["收盘"])


def evaluate_decision(
    decision: dict,
    kline: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    max_hold_days: int = MAX_HOLD_DAYS,
) -> Settlement | None:
    """评估单个 open 决策是否结算。未触发返回 None。"""
    entry_price = float(decision["entry_price"])
    stop_loss = decision.get("stop_loss")
    target_price = decision.get("target_price")
    sign = _direction_sign(decision["action"])
    decision_date = str(decision["timestamp"])[:10]

    rows = kline[kline["日期"] > decision_date].sort_values("日期").reset_index(drop=True)
    if rows.empty:
        return None

    pending_trigger: str | None = None  # 一字板递延中的触发类型
    for i in range(len(rows)):
        row = rows.iloc[i]
        hold_days = i + 1

        if pending_trigger is not None:
            # 一字板递延中:等待打开首日,以开盘价结算
            if _is_one_word_board(row):
                continue
            return _settle(
                decision,
                pending_trigger,
                str(row["日期"]),
                float(row["开盘"]),
                hold_days,
                entry_price,
                sign,
                benchmark,
            )

        hit_stop = stop_loss is not None and float(row["最低"]) <= float(stop_loss)
        hit_target = target_price is not None and float(row["最高"]) >= float(target_price)

        if hit_stop or hit_target:
            trigger = "hit_stop" if hit_stop else "hit_target"  # 同日止损优先
            if _is_one_word_board(row):
                pending_trigger = trigger  # 未成交,递延
                continue
            price = float(stop_loss) if trigger == "hit_stop" else float(target_price)
            return _settle(
                decision, trigger, str(row["日期"]), price, hold_days, entry_price, sign, benchmark
            )

        if hold_days >= max_hold_days:
            return _settle(
                decision,
                "expired",
                str(row["日期"]),
                float(row["收盘"]),
                hold_days,
                entry_price,
                sign,
                benchmark,
            )

    return None  # 行数不足或一字板未打开:继续 open


def _settle(
    decision: dict,
    status: str,
    settle_date: str,
    settle_price: float,
    hold_days: int,
    entry_price: float,
    sign: float,
    benchmark: pd.DataFrame | None,
) -> Settlement:
    decision_return = sign * (settle_price - entry_price) / entry_price
    benchmark_return: float | None = None
    decision_excess: float | None = None
    if benchmark is not None and not benchmark.empty:
        entry_bench = _bench_close_on_or_before(benchmark, str(decision["timestamp"])[:10])
        settle_bench = _bench_close_on_or_before(benchmark, settle_date)
        if entry_bench and settle_bench:
            benchmark_return = sign * (settle_bench - entry_bench) / entry_bench
            decision_excess = decision_return - benchmark_return
    return Settlement(
        status=status,
        settle_date=settle_date,
        settle_price=settle_price,
        hold_days=hold_days,
        decision_return=decision_return,
        benchmark_return=benchmark_return,
        decision_excess=decision_excess,
        decision_hit=decision_return > 0,
    )
