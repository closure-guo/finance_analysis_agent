"""stage-b 人工验证脚本：插入历史观点 → 跑真实行情盯市 → 落地净值/指标。

用法: uv run python tests/scripts/stage_b_manual_verify.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finance_agent.outcome.track_record.marking import (  # noqa: E402
    mark_open_predictions,
    run_daily_marking,
)
from finance_agent.outcome.track_record.model import (  # noqa: E402
    init_track_record_tables,
    insert_prediction,
    list_daily_marks,
    list_predictions,
)

DB = Path(__file__).resolve().parents[2] / "data" / "gui-test-sessions.db"

PREDICTIONS = [
    {
        "source_type": "live",
        "symbol": "600519.SH",
        "symbol_name": "贵州茅台",
        "direction": "long",
        "entry_price": 1450.0,
        "target_price": 1600.0,
        "horizon_days": 252,
        "confidence": 0.72,
        "langfuse_trace_id": "manual-verify-600519",
        "rationale_snapshot": {"source": "stage-b manual verify", "view": "高档白酒动销回暖"},
        "days_ago": 15,
    },
    {
        "source_type": "live",
        "symbol": "300750.SZ",
        "symbol_name": "宁德时代",
        "direction": "short",
        "entry_price": 210.0,
        "target_price": 180.0,
        "horizon_days": 252,
        "confidence": 0.6,
        "langfuse_trace_id": "manual-verify-300750",
        "rationale_snapshot": {"source": "stage-b manual verify", "view": "排产不及预期"},
        "days_ago": 10,
    },
    {
        "source_type": "live",
        "symbol": "601318.SH",
        "symbol_name": "中国平安",
        "direction": "long",
        "entry_price": 52.0,
        "horizon_days": 252,
        "confidence": 0.55,
        "langfuse_trace_id": "manual-verify-601318",
        "rationale_snapshot": {"source": "stage-b manual verify", "view": "负债端修复"},
        "days_ago": 5,
    },
]


def main() -> None:
    init_track_record_tables(db_path=DB)
    existing = list_predictions(db_path=DB)
    seeded = {
        p["langfuse_trace_id"]
        for p in existing
        if p.get("langfuse_trace_id", "").startswith("manual-verify")
    }
    for spec in PREDICTIONS:
        if spec["langfuse_trace_id"] in seeded:
            print(f"skip (already seeded): {spec['symbol']}")
            continue
        created = (datetime.now() - timedelta(days=spec.pop("days_ago"))).isoformat()
        insert_prediction({**spec, "created_at": created}, db_path=DB, status="open")
        print(f"inserted: {spec['symbol']} {spec['direction']} @ {spec['entry_price']}")

    print("--- 跑真实行情盯市（akshare）---")
    marked = mark_open_predictions(db_path=DB)
    print(f"marked points: {len(marked)}")
    result = run_daily_marking(db_path=DB)
    print(f"daily marking result: {result}")

    for p in list_predictions(db_path=DB):
        marks = list_daily_marks(db_path=DB, prediction_id=p["prediction_id"])
        print(f"{p['symbol']} {p['direction']} status={p['status']} marks={len(marks)}")


if __name__ == "__main__":
    main()
