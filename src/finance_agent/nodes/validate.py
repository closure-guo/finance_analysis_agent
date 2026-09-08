"""validate_financials: 勾稽校验节点 — 三大报表数据质量验证。

在 compute_metrics 之前执行，硬等式失败时短路终止。
"""

from __future__ import annotations

from finance_agent.metrics.validate import validate_financials


def validate_node(state: dict) -> dict:
    """执行勾稽校验，结果写入 state。

    Returns
    -------
    dict
        {"validation_result": "PASS" | "FAIL", "validation_warnings": list[str]}
    """
    bs = state.get("balance_sheet")
    inc = state.get("income_statement")
    cf = state.get("cash_flow_statement")

    if bs is None or inc is None or cf is None:
        return {
            "validation_result": "FAIL",
            "validation_warnings": ["勾稽校验跳过：三大报表数据缺失"],
        }

    result = validate_financials(bs, inc, cf)
    return {
        "validation_result": result["result"],
        "validation_warnings": result["warnings"],
    }


# ── toolize-price-levels：交易价位 sanity 校验（确定性，LLM 不参与）──

_ENTRY_DEVIATION_LIMIT = 0.15  # entry 距最新收盘偏差上限（防 LLM 报无关价位）


def _plan_direction(action: str) -> str | None:
    """buy→long / sell→short；hold/watch 无价位要求。"""
    if action == "buy":
        return "long"
    if action == "sell":
        return "short"
    return None


def validate_trade_prices(state: dict) -> dict:
    """校验 trader 价位：价格关系 / entry 距现价偏差 / 工具参考带。

    三路结果写入 price_check.result：pass（含跳过）/ fail（打回）/ corrected
    （按工具参考带修正，price_level_corrected 可观测）。校验纯规则，无 LLM。
    """
    plan = state.get("trader_plan") or {}
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump()

    action = str(plan.get("action") or "")
    direction = _plan_direction(action)
    if direction is None:
        return {"price_check": {"result": "pass", "note": "hold/watch 无价位要求"}}

    entry = plan.get("entry_price")
    stop = plan.get("stop_loss")
    target = plan.get("target_price")
    if entry is None:
        return {"price_check": {"result": "pass", "note": "价位缺失（schema 可选），跳过校验"}}

    levels = state.get("price_levels") or {}
    if not levels.get("available"):
        return {
            "price_check": {
                "result": "pass",
                "note": f"price_levels 不可用（{levels.get('reason', 'unknown')}），跳过校验",
            }
        }

    kline = state.get("kline")
    if kline is None or len(kline) == 0:
        return {"price_check": {"result": "pass", "note": "无行情数据，跳过校验"}}
    close = float(kline["收盘"].iloc[-1])

    reasons: list[str] = []

    # 1. 价格关系（三者齐备才校验关系）
    if stop is not None and target is not None:
        if direction == "long" and not (stop < entry < target):
            reasons.append(
                f"价格关系违规（long 要求 stop<entry<target，实际 {stop}/{entry}/{target}）"
            )
        if direction == "short" and not (stop > entry > target):
            reasons.append(
                f"价格关系违规（short 要求 stop>entry>target，实际 {stop}/{entry}/{target}）"
            )

    # 2. entry 距最新收盘偏差
    if abs(entry - close) / close > _ENTRY_DEVIATION_LIMIT:
        reasons.append(f"entry {entry} 距最新收盘 {close} 偏差超 {_ENTRY_DEVIATION_LIMIT:.0%}")

    # 3. 放宽带（stop/target 落在近期交易区间 ±2ATR 内）
    full_band = levels.get("full_band") or []
    if len(full_band) == 2 and stop is not None and target is not None:
        lo, hi = float(full_band[0]), float(full_band[1])
        for label, v in (("stop", stop), ("target", target)):
            if not (lo <= v <= hi):
                reasons.append(f"{label} {v} 落在参考带 [{lo}, {hi}] 之外")

    if not reasons:
        return {"price_check": {"result": "pass"}}

    reason = "；".join(reasons)
    attempts = int(state.get("price_check_attempts") or 0)
    if attempts < 1:
        feedback = (
            f"价位 sanity 校验未通过：{reason}。"
            f"请参考价位参考带重出（entry_ref={levels.get('entry_ref')}，"
            f"stop_band_long={levels.get('stop_band_long')}，"
            f"target_band_long={levels.get('target_band_long')}，"
            f"{'long: stop<entry<target' if direction == 'long' else 'short: stop>entry>target'}）"
        )
        return {
            "price_check": {"result": "fail", "reason": reason},
            "price_check_feedback": feedback,
            "price_check_attempts": attempts + 1,
        }

    # 二次失败：按工具参考带修正（可观测，不静默）
    corrected = correct_prices(plan, levels, action)
    return {
        "trader_plan": corrected,
        "price_check": {"result": "corrected", "reason": reason},
        "price_level_corrected": True,
        "price_level_correction_reason": reason,
    }


def correct_prices(plan: dict, levels: dict, action: str) -> dict:
    """按工具参考带修正价位（确定性）：entry=entry_ref，stop/target=参考带中值。

    short 镜像：stop=close±ATR 带中值对称外推，target 反向。返回新 dict，
    不修改原 plan（trader_plan 整体替换进 state）。
    """
    direction = _plan_direction(action) or "long"
    close = float(levels.get("entry_ref") or 0)
    atr = float(levels.get("atr") or 0)
    stop_band = levels.get("stop_band_long") or {}
    target_band = levels.get("target_band_long") or {}

    corrected = dict(plan)
    corrected["entry_price"] = close
    if direction == "long":
        corrected["stop_loss"] = (
            (float(stop_band["low"]) + float(stop_band["high"])) / 2
            if stop_band
            else close - 1.5 * atr
        )
        corrected["target_price"] = (
            (float(target_band["low"]) + float(target_band["high"])) / 2
            if target_band
            else close + 3 * atr
        )
    else:
        # short 镜像：stop 在上方 1-2ATR 带中值，target 在下方 2-4ATR 带中值
        corrected["stop_loss"] = close + 1.5 * atr
        corrected["target_price"] = close - 3 * atr
    corrected["price_level_corrected"] = True
    corrected["price_level_correction_reason"] = "sanity 校验二次未通过，按工具参考带修正"
    return corrected
