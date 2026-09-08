"""predictions 日批判定 job(add-track-record):遍历 open 观点 → 拉行情 → 判定 → 落状态。

与旧 settle_open_decisions(止损/目标/超期)不同:horizon 到点按区间超额判定 win/loss/neutral;
superseded(同标的新观点方向相反/目标价不同)立即按现价结算旧观点;连续无行情标 unresolvable。
幂等:update_prediction_status 前不重复处理已非 open 的观点;失败隔离:单观点异常跳过不中断整批。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from finance_agent.outcome.track_record.judgment import resolve_prediction, should_supersede
from finance_agent.outcome.track_record.model import (
    list_predictions,
    update_prediction_status,
)

logger = logging.getLogger(__name__)

STALE_DAYS = int(__import__("os").getenv("DECISION_STALE_DAYS", "5"))
BENCHMARK_CODE = "000300"


def _code(symbol: str) -> str:
    """'600519.SH' → '600519'。"""
    return symbol.split(".")[0]


def _normalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["日期"] = df["日期"].astype(str).str[:10]
    return df


def _is_stale(kline: pd.DataFrame | None, benchmark: pd.DataFrame | None) -> bool:
    if kline is None or kline.empty or benchmark is None or benchmark.empty:
        return False
    ticker_last = str(kline.iloc[-1]["日期"])
    bench_dates = [str(d) for d in benchmark["日期"]]
    return len([d for d in bench_dates if d > ticker_last]) >= STALE_DAYS


def settle_open_predictions(
    *,
    client: Any = None,
    db_path: str | Path | None = None,
    kline_days: int = 280,
) -> dict[str, int]:
    """遍历 open predictions 日批判定。返回 {settled, superseded, unresolvable, skipped, errors}。"""
    if client is None:
        from finance_agent.data.akshare_client import AKShareClient

        client = AKShareClient()
    result = {"settled": 0, "superseded": 0, "unresolvable": 0, "skipped": 0, "errors": 0}
    try:
        open_preds = list_predictions(status="open", db_path=db_path)
    except Exception as e:  # noqa: BLE001
        logger.error("读取 open 观点失败,本批终止: %s", e)
        result["errors"] += 1
        return result

    benchmark: pd.DataFrame | None
    try:
        benchmark = client.fetch_index_kline(BENCHMARK_CODE, days=kline_days)
        if benchmark is not None and not benchmark.empty:
            benchmark = _normalize_dates(benchmark)
    except Exception as e:  # noqa: BLE001
        logger.warning("基准行情拉取失败,本批按无基准降级: %s", e)
        benchmark = None

    # 按 symbol 分组,组内按 created_at 升序:同标的多条 open → 旧观点被新观点 supersede
    by_symbol: dict[str, list[dict]] = {}
    for p in open_preds:
        by_symbol.setdefault(p["symbol"], []).append(p)
    for sym, group in by_symbol.items():
        group.sort(key=lambda p: str(p["created_at"]))
        if len(group) > 1:
            for old in group[:-1]:
                new = group[-1]
                if should_supersede(old, new):
                    try:
                        kline = client.fetch_kline(_code(sym), days=kline_days)
                        if kline is not None and not kline.empty:
                            kline = _normalize_dates(kline)
                        exit_price = (
                            float(kline.iloc[-1]["收盘"])
                            if kline is not None and not kline.empty
                            else None
                        )
                        if exit_price is None:
                            result["skipped"] += 1
                            continue
                        entry = float(old["entry_price"])
                        sign = 1.0 if old["direction"] == "long" else -1.0
                        raw = sign * (exit_price / entry - 1.0) if entry > 0 else 0.0
                        update_prediction_status(
                            old["prediction_id"],
                            {
                                "status": "resolved_win"
                                if raw > 0
                                else ("resolved_loss" if raw < 0 else "resolved_neutral"),
                                "exit_price": exit_price,
                                "raw_return": round(raw, 6),
                                "resolution_rule": "superseded",
                                "resolved_at": str(kline.iloc[-1]["日期"]),
                            },
                            db_path,
                        )
                        result["superseded"] += 1
                    except Exception as e:  # noqa: BLE001
                        logger.warning("superseded 判定失败 %s: %s", old["prediction_id"], e)
                        result["errors"] += 1

    # 剩余 open 观点:horizon 到点判定 / 长期无行情 unresolvable
    remaining = list_predictions(status="open", db_path=db_path)
    for p in remaining:
        try:
            kline = client.fetch_kline(_code(p["symbol"]), days=kline_days)
            if kline is not None and not kline.empty:
                kline = _normalize_dates(kline)
            created = str(p["created_at"])[:10]
            has_new_rows = (
                kline is not None and not kline.empty and not kline[kline["日期"] > created].empty
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("行情拉取失败,本次跳过 %s: %s", p["prediction_id"], e)
            result["errors"] += 1
            continue

        if not has_new_rows:
            if _is_stale(kline, benchmark):
                update_prediction_status(
                    p["prediction_id"],
                    {
                        "status": "unresolvable",
                        "resolution_rule": "stale_no_market",
                        "resolved_at": str(p["created_at"])[:10],
                    },
                    db_path,
                )
                result["unresolvable"] += 1
            else:
                result["skipped"] += 1
            continue

        try:
            resolution = resolve_prediction(p, kline, benchmark)
        except Exception as e:  # noqa: BLE001
            logger.warning("判定评估异常,本次跳过 %s: %s", p["prediction_id"], e)
            result["errors"] += 1
            continue
        if resolution is None:
            result["skipped"] += 1
            continue
        try:
            update_prediction_status(
                p["prediction_id"],
                {
                    "status": resolution.status,
                    "exit_price": resolution.exit_price,
                    "raw_return": resolution.raw_return,
                    "excess_return": resolution.excess_return,
                    "resolution_rule": resolution.resolution_rule,
                    "resolved_at": str(p["created_at"])[:10],
                },
                db_path,
            )
            result["settled"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("落库异常,本次跳过 %s: %s", p["prediction_id"], e)
            result["errors"] += 1

    return result
