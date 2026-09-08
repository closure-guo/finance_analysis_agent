"""expose-decision-outcomes:store 层只读查询函数(list_decisions / decision_stats)。"""

import pytest

from finance_agent.outcome.store import (
    DECISION_STATUSES,
    decision_stats,
    init_decision_log,
    insert_decision,
    list_decisions,
)

BASE = {
    "session_id": "sess-1",
    "timestamp": "2026-09-01T10:00:00",
    "ticker": "600519",
    "name": "贵州茅台",
    "action": "buy",
    "entry_price": 100.0,
    "stop_loss": 90.0,
    "target_price": 120.0,
    "confidence": 0.8,
    "position_size": 0.3,
}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "decisions.db"
    init_decision_log(path)
    return path


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_decision(rec, db_path=db)


def _settle(db, decision_id, **fields):
    from finance_agent.outcome.store import mark_settled

    settled = {
        "status": "hit_target",
        "settled_at": "2026-09-10T15:00:00",
        "settle_price": 115.0,
        "hold_days": 5,
        "decision_return": 0.15,
        "benchmark_return": 0.05,
        "decision_excess": 0.10,
    }
    settled.update(fields)
    mark_settled(decision_id, settled, db_path=db)


def test_list_decisions_empty(db):
    assert list_decisions(db_path=db) == []


def test_list_decisions_sorted_desc_by_timestamp(db):
    _insert(db, timestamp="2026-09-01T10:00:00", ticker="600519")
    _insert(db, timestamp="2026-09-02T10:00:00", ticker="300308")
    rows = list_decisions(db_path=db)
    assert [r["ticker"] for r in rows] == ["300308", "600519"]


def test_list_decisions_filter_ticker_and_status(db):
    _insert(db, ticker="600519")
    d2 = _insert(db, ticker="300308")
    _settle(db, d2)
    rows = list_decisions(ticker="600519", db_path=db)
    assert [r["ticker"] for r in rows] == ["600519"]
    rows = list_decisions(status="hit_target", db_path=db)
    assert [r["decision_id"] for r in rows] == [d2]
    rows = list_decisions(ticker="600519", status="hit_target", db_path=db)
    assert rows == []


def test_list_decisions_limit(db):
    for i in range(5):
        _insert(db, ticker=f"T{i}")
    assert len(list_decisions(limit=2, db_path=db)) == 2
    assert len(list_decisions(limit=0, db_path=db)) == 1  # 下限钳制为 1
    assert len(list_decisions(limit=9999, db_path=db)) == 5  # 上限钳制为 1000


def test_decision_statuses_enum():
    assert DECISION_STATUSES == ("open", "hit_stop", "hit_target", "expired")


def test_stats_empty_table(db):
    s = decision_stats(db_path=db)
    assert s["total"] == 0 and s["open"] == 0 and s["settled"] == 0
    assert s["win_rate"] is None and s["avg_return"] is None and s["avg_excess"] is None


def test_stats_all_open_no_settled(db):
    _insert(db)
    _insert(db)
    s = decision_stats(db_path=db)
    assert s["total"] == 2 and s["open"] == 2 and s["settled"] == 0
    assert s["win_rate"] is None and s["avg_return"] is None


def test_stats_settled_metrics_and_null_excess_excluded(db):
    _insert(db)  # open,不计入
    d1 = _insert(db, ticker="A")
    _settle(db, d1, decision_return=0.10, benchmark_return=0.05, decision_excess=0.05)
    d2 = _insert(db, ticker="B")
    _settle(
        db,
        d2,
        status="hit_stop",
        decision_return=-0.05,
        benchmark_return=None,
        decision_excess=None,
    )
    s = decision_stats(db_path=db)
    assert s["total"] == 3 and s["open"] == 1 and s["settled"] == 2
    assert s["by_status"] == {"open": 1, "hit_target": 1, "hit_stop": 1}
    # 胜率 = 1/2；均值 = (0.10-0.05)/2；excess 只算 d1 → 0.05
    assert s["win_rate"] == 0.5
    assert s["avg_return"] == 0.025
    assert s["avg_excess"] == 0.05
