"""add-track-record Task 1:predictions 数据模型(append-only + 冻结守卫 + 迁移)。"""

import pytest

from finance_agent.outcome.track_record.model import (
    PREDICTIONS_STATUSES,
    FrozenFieldError,
    init_predictions,
    insert_prediction,
    list_predictions,
    migrate_decision_log,
    prediction_stats,
    update_prediction_status,
)

BASE = {
    "source_type": "live",
    "symbol": "600519.SH",
    "symbol_name": "贵州茅台",
    "direction": "long",
    "entry_price": 100.0,
    "target_price": 120.0,
    "horizon_days": 252,
    "confidence": 0.8,
    "benchmark": "000300.SH",
    "rationale_snapshot": {"markdown": "原文快照", "decision": {"action": "buy"}},
}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "track.db"
    init_predictions(path)
    return path


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_prediction(rec, db_path=db)


def test_statuses_enum():
    assert PREDICTIONS_STATUSES == (
        "open",
        "resolved_win",
        "resolved_loss",
        "resolved_neutral",
        "unresolvable",
    )


def test_insert_and_list(db):
    _insert(db)
    rows = list_predictions(db_path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["direction"] == "long" and row["source_type"] == "live"
    assert row["status"] == "open"
    assert row["created_at"]  # 服务端生成


def test_frozen_field_update_raises(db):
    pid = _insert(db)
    with pytest.raises(FrozenFieldError):
        update_prediction_status(pid, {"direction": "short"}, db_path=db)


def test_status_update_allowed(db):
    pid = _insert(db)
    update_prediction_status(
        pid,
        {
            "status": "resolved_win",
            "exit_price": 110.0,
            "raw_return": 0.1,
            "excess_return": 0.05,
            "resolution_rule": "expiry",
            "resolved_at": "2026-09-02",
        },
        db_path=db,
    )
    row = list_predictions(db_path=db)[0]
    assert row["status"] == "resolved_win" and row["exit_price"] == 110.0
    assert row["direction"] == "long"  # 冻结字段未被改动


def test_list_filter_and_pagination(db):
    _insert(db, symbol="600519.SH")
    _insert(db, symbol="300308.SZ")
    assert len(list_predictions(ticker="600519", db_path=db)) == 1
    assert len(list_predictions(status="open", db_path=db)) == 2
    assert len(list_predictions(source_type="backtest", db_path=db)) == 0
    assert len(list_predictions(limit=1, db_path=db)) == 1


def test_stats_empty(db):
    s = prediction_stats(db_path=db)
    assert s["total"] == 0 and s["open"] == 0 and s["win_rate"] is None


def test_migrate_decision_log(db, tmp_path):
    # 预置 decision_log 数据(复用 outcome.store DDL)
    from finance_agent.outcome.store import init_decision_log, insert_decision

    init_decision_log(db)
    insert_decision(
        {
            "session_id": "s",
            "timestamp": "2026-09-01T10:00:00",
            "ticker": "600519",
            "name": "贵州茅台",
            "action": "buy",
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "confidence": 0.8,
        },
        db_path=db,
    )
    n = migrate_decision_log(db_path=db)
    assert n == 1
    rows = list_predictions(db_path=db)
    assert rows[0]["symbol"] == "600519.SH"
    assert rows[0]["direction"] == "long"
