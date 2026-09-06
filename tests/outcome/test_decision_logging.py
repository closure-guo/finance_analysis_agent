"""api._persist_decision_log:add-track-record 全量观点落 predictions 的边界。

(原 decision_log 只记 approve 的行为已由 track-record 全量记录取代——见
tests/outcome/test_track_record_ingest.py 覆盖 approve/reject/no-price 主路径;
本文件覆盖 kline 兜底、无决策跳过、trace 关联等边界。)
"""

import pandas as pd

from finance_agent.api import _persist_decision_log
from finance_agent.outcome.track_record.model import init_predictions, list_predictions


def _db(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    init_predictions(db)
    monkeypatch.setattr("finance_agent.outcome.track_record.model._default_db_path", lambda: db)
    return db


def _accumulated(**overrides):
    base = {
        "fund_manager_decision": "approve",
        "final_trade_decision": {
            "action": "buy",
            "confidence": 0.8,
            "reasoning": "x",
            "entry_price": None,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "position_size": "30%",
        },
        "langfuse_trace_id": "trace-1",
        "stock_quote": {"price": 100.0},
    }
    base.update(overrides)
    return base


def test_quote_price_used(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    _persist_decision_log(_accumulated(), "sess-1", "600519", "贵州茅台")
    row = list_predictions(db_path=db)[0]
    assert row["entry_price"] == 100.0  # quote 回填,非 LLM 的 None
    assert row["direction"] == "long"
    assert row["langfuse_trace_id"] == "trace-1"


def test_kline_close_fallback(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    acc = _accumulated(stock_quote=None)
    acc["kline"] = pd.DataFrame([{"日期": "2026-08-01", "收盘": 99.5}])
    _persist_decision_log(acc, "sess-1", "600519", "茅台")
    assert list_predictions(db_path=db)[0]["entry_price"] == 99.5


def test_sell_maps_short(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    _persist_decision_log(
        _accumulated(
            final_trade_decision={"action": "sell", "confidence": 0.6, "entry_price": None}
        ),
        "s",
        "300308",
        "中际旭创",
    )
    row = list_predictions(db_path=db)[0]
    assert row["direction"] == "short"
    assert row["symbol"] == "300308.SZ"  # 3/0 开头 → SZ


def test_no_decision_skips(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    _persist_decision_log(_accumulated(final_trade_decision=None), "s", "600519", "茅台")
    assert list_predictions(db_path=db) == []


def test_failure_does_not_raise(monkeypatch, tmp_path, caplog):
    import logging
    from unittest.mock import patch

    _db(monkeypatch, tmp_path)
    # 构造落库失败:ingest 的 insert_prediction 抛错(api 委托共享入口后 patch 此处)
    acc = _accumulated(final_trade_decision={"action": "buy", "confidence": 0.8, "entry_price": 1})
    with (
        patch(
            "finance_agent.outcome.track_record.ingest.insert_prediction",
            side_effect=RuntimeError("db down"),
        ),
        caplog.at_level(logging.ERROR),
    ):
        _persist_decision_log(acc, "s", "600519", "茅台")  # 不抛
    assert any("prediction 落库失败" in r.message for r in caplog.records)
