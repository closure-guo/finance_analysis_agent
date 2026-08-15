"""decision_log DDL + CRUD:幂等建表、插入、open 查询、结算更新。"""

import pytest

from finance_agent.outcome import store


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.db"
    store.init_decision_log(path)
    return path


def _record(**overrides):
    base = {
        "decision_id": "d_test001",
        "session_id": "sess-1",
        "langfuse_trace_id": "trace-abc",
        "timestamp": "2026-08-10T15:30:00",
        "ticker": "600519",
        "name": "贵州茅台",
        "action": "buy",
        "entry_price": 1700.0,
        "stop_loss": 1600.0,
        "target_price": 1900.0,
        "confidence": 0.8,
        "position_size": 0.3,
    }
    base.update(overrides)
    return base


class TestInit:
    def test_idempotent_init(self, db):
        # 重复执行不报错(幂等 DDL)
        store.init_decision_log(db)
        store.init_decision_log(db)

    def test_table_and_index_created(self, db):
        import sqlite3

        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        conn.close()
        assert "decision_log" in tables
        assert "idx_decision_log_status" in indexes


class TestInsertAndQuery:
    def test_insert_returns_id_and_open_query(self, db):
        decision_id = store.insert_decision(_record(), db)
        assert decision_id == "d_test001"
        rows = store.get_open_decisions(db)
        assert len(rows) == 1
        row = rows[0]
        assert row["ticker"] == "600519"
        assert row["action"] == "buy"
        assert row["entry_price"] == 1700.0
        assert row["status"] == "open"
        assert row["langfuse_trace_id"] == "trace-abc"

    def test_nullable_fields(self, db):
        store.insert_decision(
            _record(
                decision_id="d_test002",
                langfuse_trace_id=None,
                name=None,
                stop_loss=None,
                target_price=None,
                confidence=None,
                position_size=None,
            ),
            db,
        )
        row = store.get_open_decisions(db)[0]
        assert row["stop_loss"] is None
        assert row["position_size"] is None

    def test_generates_id_when_missing(self, db):
        # decision_id 未提供时生成 f"d_{uuid4().hex[:12]}"(brief 要点 4)
        record = _record()
        del record["decision_id"]
        decision_id = store.insert_decision(record, db)
        assert decision_id.startswith("d_")
        assert len(decision_id) == 14  # "d_" + 12 hex
        row = store.get_open_decisions(db)[0]
        assert row["decision_id"] == decision_id


class TestMarkSettled:
    def test_settled_row_leaves_open_set(self, db):
        store.insert_decision(_record(), db)
        store.mark_settled(
            "d_test001",
            {
                "status": "hit_target",
                "settled_at": "2026-08-12T16:00:00",
                "settle_price": 1900.0,
                "hold_days": 2,
                "decision_return": 0.1176,
                "benchmark_return": 0.01,
                "decision_excess": 0.1076,
            },
            db,
        )
        assert store.get_open_decisions(db) == []

    def test_settled_fields_persisted(self, db):
        import sqlite3

        store.insert_decision(_record(), db)
        store.mark_settled(
            "d_test001",
            {
                "status": "hit_stop",
                "settled_at": "2026-08-12T16:00:00",
                "settle_price": 1600.0,
                "hold_days": 2,
                "decision_return": -0.0588,
                "benchmark_return": 0.005,
                "decision_excess": -0.0638,
            },
            db,
        )
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM decision_log WHERE decision_id='d_test001'").fetchone()
        conn.close()
        assert row["status"] == "hit_stop"
        assert row["settle_price"] == 1600.0
        assert row["hold_days"] == 2
        assert abs(row["decision_return"] - (-0.0588)) < 1e-9
