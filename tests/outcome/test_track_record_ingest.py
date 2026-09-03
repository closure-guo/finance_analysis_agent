"""add-track-record Task 3:观点全量记录(_persist_decision_log → predictions)。"""

from finance_agent.api import _persist_decision_log
from finance_agent.outcome.track_record.model import init_predictions, list_predictions


def _db(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    init_predictions(db)
    monkeypatch.setattr("finance_agent.outcome.track_record.model._default_db_path", lambda: db)
    return db


def test_approve_buy_records_long(monkeypatch, tmp_path):
    _db(monkeypatch, tmp_path)
    _persist_decision_log(
        {
            "fund_manager_decision": "approve",
            "final_trade_decision": {
                "action": "buy",
                "confidence": 0.8,
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "target_price": 120.0,
                "position_size": "30%",
            },
            "stock_quote": {"price": 100.0},
        },
        "sess-1",
        "600519",
        "贵州茅台",
    )
    rows = list_predictions(db_path=tmp_path / "t.db")
    assert len(rows) == 1
    assert rows[0]["direction"] == "long" and rows[0]["source_type"] == "live"
    assert rows[0]["entry_price"] == 100.0


def test_reject_also_records(monkeypatch, tmp_path):
    _db(monkeypatch, tmp_path)
    _persist_decision_log(
        {
            "fund_manager_decision": "reject",
            "final_trade_decision": {
                "action": "hold",
                "confidence": 0.5,
                "entry_price": 100.0,
            },
            "stock_quote": {"price": 100.0},
        },
        "sess-1",
        "600519",
        "贵州茅台",
    )
    rows = list_predictions(db_path=tmp_path / "t.db")
    assert len(rows) == 1
    assert rows[0]["direction"] == "neutral"  # hold → neutral
    assert rows[0]["status"] == "open"


def test_no_price_archives_unresolvable(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    _persist_decision_log(
        {
            "fund_manager_decision": "approve",
            "final_trade_decision": {"action": "buy", "confidence": 0.8},
            "stock_quote": None,
        },
        "sess-1",
        "600519",
        "贵州茅台",
    )
    rows = list_predictions(db_path=db)
    assert len(rows) == 1
    assert rows[0]["status"] == "unresolvable"
    assert rows[0]["entry_price"] is None


def test_no_decision_skips(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    _persist_decision_log(
        {"fund_manager_decision": "approve", "final_trade_decision": None},
        "sess-1",
        "600519",
        "贵州茅台",
    )
    assert list_predictions(db_path=db) == []
