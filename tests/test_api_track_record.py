"""add-track-record Task 4:track-record 只读 API 端点测试。"""

from fastapi.testclient import TestClient

from finance_agent.api import app
from finance_agent.outcome.track_record.model import (
    init_predictions,
    insert_prediction,
    update_prediction_status,
)

BASE = {
    "source_type": "live",
    "symbol": "600519.SH",
    "symbol_name": "贵州茅台",
    "direction": "long",
    "entry_price": 100.0,
    "horizon_days": 252,
    "confidence": 0.8,
    "rationale_snapshot": {"action": "buy"},
    "created_at": "2026-09-01T10:00:00",
}


def _use_db(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    init_predictions(db)
    monkeypatch.setattr("finance_agent.outcome.track_record.model._default_db_path", lambda: db)
    return db


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_prediction(rec, db_path=db)


def test_overview_empty(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    resp = TestClient(app).get("/api/v1/track-record/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0 and data["win_rate"] is None
    assert data["as_of"] and data["disclaimer"]
    assert data["insufficient_sample"] is True


def test_overview_with_settled(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    for i in range(3):
        pid = _insert(db, symbol=f"{i}.SH", created_at=f"2026-09-0{i + 1}T10:00:00")
        update_prediction_status(
            pid,
            {
                "status": "resolved_win" if i < 2 else "resolved_loss",
                "raw_return": 0.1,
                "excess_return": 0.05,
            },
            db_path=db,
        )
    data = TestClient(app).get("/api/v1/track-record/overview").json()
    assert data["total"] == 3 and data["settled"] == 3
    # 显著性门槛:settled < 10 → 不展示胜率
    assert data["win_rate"] is None and data["insufficient_sample"] is True


def test_overview_win_rate_after_10_settled(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    for i in range(10):
        pid = _insert(db, symbol=f"{i}.SH", created_at=f"2026-09-{i + 1:02d}T10:00:00")
        update_prediction_status(
            pid,
            {
                "status": "resolved_win" if i < 7 else "resolved_loss",
                "raw_return": 0.1,
                "excess_return": 0.05,
            },
            db_path=db,
        )
    data = TestClient(app).get("/api/v1/track-record/overview").json()
    assert data["settled"] == 10 and data["insufficient_sample"] is False
    assert data["win_rate"] == 0.7


def test_overview_source_filter(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db, source_type="live")
    _insert(db, source_type="backtest")
    live = TestClient(app).get("/api/v1/track-record/overview", params={"source": "live"}).json()
    assert live["total"] == 1


def test_predictions_list_default_all_statuses(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    _insert(db)
    pid = _insert(db, symbol="300308.SZ", created_at="2026-09-02T10:00:00")
    update_prediction_status(pid, {"status": "resolved_loss"}, db_path=db)
    items = TestClient(app).get("/api/v1/track-record/predictions").json()["predictions"]
    assert len(items) == 2  # 默认含 loss


def test_predictions_filter_and_page(monkeypatch, tmp_path):
    db = _use_db(monkeypatch, tmp_path)
    for i in range(5):
        _insert(db, symbol=f"6{i}.SH", created_at=f"2026-09-0{i + 1}T10:00:00")
    c = TestClient(app)
    assert (
        len(
            c.get("/api/v1/track-record/predictions", params={"status": "open"}).json()[
                "predictions"
            ]
        )
        == 5
    )
    page1 = c.get("/api/v1/track-record/predictions", params={"page": 1, "page_size": 2}).json()
    assert len(page1["predictions"]) == 2 and page1["total"] == 5
