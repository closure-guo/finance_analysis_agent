"""回测数据快照：时点截断 + 可审计元信息（spec decision-backtest「历史离线回放」；design D5）。

前视偏差防控：行情按日期 ≤ T；财报按披露截止日（法定期限近似：Q1→04-30、
H1→08-31、Q3→10-31、年报→次年 04-30）而非报告期；新闻/事件按日期 ≤ T；
stock_quote / industry_pe 等纯当下数据剔除并在 metadata.excluded_fields 记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

_EXCLUDED_POINT_IN_TIME = ("stock_quote", "industry_pe")


@dataclass
class SnapshotResult:
    state: dict
    metadata: dict = field(default_factory=dict)


def disclosure_deadline(period_end: str) -> str:
    """A 股法定披露截止日近似（报告期期末 → 最晚披露日）。"""
    year, month = int(period_end[:4]), int(period_end[4:6])
    deadline = {(3,): "0430", (6,): "0831", (9,): "1031", (12,): "0430"}[(month,)]
    if month == 12:
        return f"{year + 1}{deadline}"
    return f"{year}{deadline}"


def _truncate_kline(df: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    dates = df["日期"].astype(str).str[:10]
    return df[dates <= decision_date].copy()


def _truncate_reports(df: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    deadlines = df["报告日"].astype(str).map(lambda d: disclosure_deadline(d))
    keep = deadlines <= decision_date.replace("-", "")
    return df[keep].copy()


def _truncate_dated_list(items: Any, decision_date: str) -> list:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, dict):
            date = str(item.get("date") or item.get("发布时间") or "")[:10]
            if not date or date <= decision_date:
                out.append(item)
        else:
            out.append(item)
    return out


def truncate_state(full_state: dict, decision_date: str) -> dict:
    """所有可得性截断的入口；不改调用方对象。"""
    out: dict = {}
    for key, value in full_state.items():
        if key in _EXCLUDED_POINT_IN_TIME:
            continue
        if key in ("kline", "benchmark_kline") and isinstance(value, pd.DataFrame):
            out[key] = _truncate_kline(value, decision_date)
        elif key in (
            "balance_sheet",
            "income_statement",
            "cash_flow_statement",
            "financial_indicators",
            "quarterly_income",
        ) and isinstance(value, pd.DataFrame):
            if "报告日" in value.columns:
                out[key] = _truncate_reports(value, decision_date)
            else:
                out[key] = value.copy()
        elif key in ("news_list", "key_events"):
            out[key] = _truncate_dated_list(value, decision_date)
        else:
            out[key] = value
    return out


def build_snapshot(code: str, decision_date: str, *, client: Any = None) -> SnapshotResult:
    """拉全量数据 → 截断 → 快照 + 审计元信息。"""
    from finance_agent.nodes.fetch import fetch_data

    base = {"stock_code": code, "enable_web_search": False}
    full = {**base, **fetch_data(base, client=client)}
    state = truncate_state(full, decision_date)
    metadata = {
        "code": code,
        "decision_date": decision_date,
        "data_cutoff": decision_date,
        "disclosure_rule": "legal-deadline-approx(Q1:0430,H1:0831,Q3:1031,FY:next-0430)",
        "excluded_fields": list(_EXCLUDED_POINT_IN_TIME),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    return SnapshotResult(state=state, metadata=metadata)
