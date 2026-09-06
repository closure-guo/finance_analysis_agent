"""expose-decision-outcomes:GET /api/decisions 与 /api/decisions/stats 端点测试。"""

from fastapi.testclient import TestClient

from finance_agent.api import app
from finance_agent.outcome.store import init_decision_log, insert_decision, mark_settled

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


def _use_db(monkeypatch, tmp_path):
    db = tmp_path / "decisions.db"
    init_decision_log(db)
    monkeypatch.setattr("finance_agent.outcome.store._default_db_path", lambda: db)
    return db


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_decision(rec, db_path=db)


def test_list_empty(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).get("/api/decisions")
    assert resp.status_code == 200 and resp.json() == []


def test_list_returns_records_with_fields(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db)
    items = TestClient(app).get("/api/decisions").json()
    assert len(items) == 1
    row = items[0]
    assert row["ticker"] == "600519" and row["action"] == "buy" and row["status"] == "open"
    for field in (
        "decision_id",
        "session_id",
        "timestamp",
        "ticker",
        "name",
        "action",
        "entry_price",
        "stop_loss",
        "target_price",
        "confidence",
        "status",
        "settled_at",
        "settle_price",
        "hold_days",
        "decision_return",
        "benchmark_return",
        "decision_excess",
    ):
        assert field in row


def test_filter_and_invalid_status(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, ticker="600519")
    _insert(db, ticker="300308")
    c = TestClient(app)
    assert len(c.get("/api/decisions", params={"ticker": "600519"}).json()) == 1
    assert len(c.get("/api/decisions", params={"ticker": "300308", "status": "open"}).json()) == 1
    assert c.get("/api/decisions", params={"status": "bogus"}).status_code == 422


def test_stats_endpoint(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db)
    d2 = _insert(db, ticker="300308")
    mark_settled(
        d2,
        {
            "status": "hit_target",
            "settled_at": "2026-09-10T15:00:00",
            "settle_price": 115.0,
            "hold_days": 5,
            "decision_return": 0.10,
            "benchmark_return": 0.05,
            "decision_excess": 0.05,
        },
        db_path=db,
    )
    s = TestClient(app).get("/api/decisions/stats").json()
    assert s["total"] == 2 and s["open"] == 1 and s["settled"] == 1
    assert s["win_rate"] == 1.0 and s["avg_return"] == 0.1 and s["avg_excess"] == 0.05


def test_stats_empty(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    s = TestClient(app).get("/api/decisions/stats").json()
    assert s["win_rate"] is None and s["avg_return"] is None
