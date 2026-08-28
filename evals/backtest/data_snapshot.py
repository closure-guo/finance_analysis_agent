"""回测数据快照：时点截断 + 可审计元信息（spec decision-backtest「历史离线回放」；design D5）。

前视偏差防控：行情按日期 ≤ T；财报按披露截止日（法定期限近似：Q1→04-30、
H1→08-31、Q3→10-31、年报→次年 04-30）而非报告期；新闻/事件按日期 ≤ T；
stock_quote / industry_pe 等纯当下数据剔除并在 metadata.excluded_fields 记录。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

_EXCLUDED_POINT_IN_TIME = ("stock_quote", "industry_pe", "peer_financials")

# 宏观记录第一个键（月份列）的值兼容 "2024-01" 与 "2024年1月" 两种格式
_MONTH_RE = re.compile(r"(\d{4})\s*[-年/.]\s*(\d{1,2})")


@dataclass
class SnapshotResult:
    state: dict
    metadata: dict = field(default_factory=dict)


def disclosure_deadline(period_end: str) -> str:
    """A 股法定披露截止日近似（报告期期末 → 最晚披露日）。

    period_end 兼容 "20240930" 与 "2024-09-30" 等格式：入口先归一化
    （去非数字字符取前 8 位）；归一后非 8 位数字或月份非季末 → 显式 ValueError。
    """
    digits = re.sub(r"\D", "", str(period_end))[:8]
    if len(digits) != 8:
        raise ValueError(f"报告期归一化后须为 8 位日期(YYYYMMDD), got {period_end!r}")
    year, month = int(digits[:4]), int(digits[4:6])
    deadline = {3: "0430", 6: "0831", 9: "1031", 12: "0430"}.get(month)
    if deadline is None:
        raise ValueError(f"报告期须为季末日期(0331/0630/0930/1231), got {period_end!r}")
    if month == 12:
        return f"{year + 1}{deadline}"
    return f"{year}{deadline}"


def _truncate_kline(df: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    dates = df["日期"].astype(str).str[:10]
    return df[dates <= decision_date].copy()


def _truncate_reports(df: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    """按披露截止截断财报/指标表；日期列兼容「报告日」与「日期」两种列名。

    报告日缺失/非法的行日期不可判 → 保守剔除（宁缺勿前视），不让整表崩溃。
    """
    date_col = next((c for c in ("报告日", "日期") if c in df.columns), None)
    if date_col is None:
        return df.copy()
    df = df.dropna(subset=[date_col])
    cutoff = decision_date.replace("-", "")

    def _disclosed_by(value: Any) -> bool:
        try:
            return disclosure_deadline(str(value)) <= cutoff
        except ValueError:
            return False

    keep = df[date_col].map(_disclosed_by)
    return df[keep].copy()


def _truncate_dated_list(items: Any, decision_date: str) -> list:
    """只保留日期可判 ≤ T 的条目；无日期/非 dict 条目保守剔除（可能前视）。"""
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("发布时间") or item.get("datetime") or "")[:10]
        if date and date <= decision_date:
            out.append(item)
    return out


def _record_month(record: dict) -> str | None:
    """从记录第一个键的值提取 year-month（"2025-01"）；无法解析返回 None。"""
    if not record:
        return None
    first_value = next(iter(record.values()))
    m = _MONTH_RE.search(str(first_value))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def _truncate_macro(macro: Any, decision_date: str) -> Any:
    """宏观指标按 月份 ≤ decision_date 月份 截断。

    每个指标为 {records: [...], as_of_date, freshness}；失败指标为空 list 原样。
    无法解析月份的条目剔除（保守：宁缺勿前视）。
    """
    if not isinstance(macro, dict):
        return macro
    cutoff = decision_date[:7]
    out: dict = {}
    for key, value in macro.items():
        if not isinstance(value, dict) or not isinstance(value.get("records"), list):
            out[key] = value
            continue
        records = [
            r
            for r in value["records"]
            if isinstance(r, dict) and (month := _record_month(r)) is not None and month <= cutoff
        ]
        out[key] = {**value, "records": records}
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
            out[key] = _truncate_reports(value, decision_date)
        elif key in ("news_list", "key_events"):
            out[key] = _truncate_dated_list(value, decision_date)
        elif key == "macro_indicators":
            out[key] = _truncate_macro(value, decision_date)
        else:
            out[key] = value
    return out


def build_snapshot(code: str, decision_date: str, *, client: Any = None) -> SnapshotResult:
    """拉全量数据 → 截断 → 快照 + 审计元信息（prompt/模型版本随快照落盘，保证可复现审计）。"""
    from evals.run import _collect_prompt_versions
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
        "prompt_versions": _collect_prompt_versions(),
        "model": os.getenv("LLM_MODEL") or "unspecified",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    return SnapshotResult(state=state, metadata=metadata)
