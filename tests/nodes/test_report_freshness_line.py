# tests/nodes/test_report_freshness_line.py
"""数据新鲜度披露（update-report-data-disclosure）：报告头部行情截止声明行。"""

from __future__ import annotations

import pandas as pd

from finance_agent.nodes.report import generate_report


def _state(kline: pd.DataFrame | None) -> dict:
    state: dict = {
        "stock_name": "拓荆科技",
        "stock_code": "688072",
        "focus_summary": "预置摘要：多空均衡，维持观望。",
    }
    if kline is not None:
        state["kline"] = kline
    return state


def test_header_contains_market_data_cutoff():
    kline = pd.DataFrame({"日期": ["2026-09-29", "2026-09-30"], "收盘": [100.0, 101.0]})
    md = generate_report(_state(kline))["final_report"]
    assert "行情数据截止: 2026-09-30" in md


def test_header_without_kline_omits_cutoff():
    md = generate_report(_state(None))["final_report"]
    assert "行情数据截止" not in md


def test_header_empty_kline_omits_cutoff():
    md = generate_report(_state(pd.DataFrame()))["final_report"]
    assert "行情数据截止" not in md
