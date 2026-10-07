"""结算报告消费端测试（issue #250：collect/build/render，口径 §1.9-v2）。"""

import pytest
from finance_agent.outcome.track_record.report import collect_settled_day_masters

from finance_agent.outcome.track_record.model import (
    init_predictions,
    insert_prediction,
    update_prediction_status,
)

BASE = {
    "source_type": "live",
    "symbol": "600519.SH",
    "direction": "long",
    "rationale_snapshot": {"markdown": "x"},
}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "report.db"
    init_predictions(path)
    return path


def _insert(db, **overrides):
    rec = dict(BASE)
    rec.update(overrides)
    return insert_prediction(rec, db_path=db)


def _settle(db, pid, **overrides):
    """把观点置为已结算（resolution_rule 非空）；overrides 覆盖默认 resolved 字段。"""
    resolved = {
        "status": "resolved_win",
        "resolved_at": "2026-11-03T15:00:00",
        "excess_return": 0.05,
        "resolution_rule": "expiry",
    }
    resolved.update(overrides)
    update_prediction_status(pid, resolved, db_path=db)


class TestCollectSettledDayMasters:
    def test_filters_duplicate_of_day_rows(self, db):
        """duplicate_of_day 行（同日重复关闭行）不进结算报告——§1.9-v2 防御过滤。"""
        keep = _insert(db)
        dup = _insert(db, symbol="000001.SZ")
        _settle(db, keep)
        _settle(
            db,
            dup,
            status="duplicate_of_day",
            excess_return=None,
            resolved_at=None,
            resolution_rule="duplicate_of_day",
        )
        settled = collect_settled_day_masters(db_path=db)
        assert [r["prediction_id"] for r in settled] == [keep]

    def test_excludes_unsettled_open_rows(self, db):
        """未结算 open 行（resolution_rule 为空）不进结算报告。"""
        settled_id = _insert(db)
        open_id = _insert(db, symbol="000001.SZ")
        _settle(db, settled_id)
        settled = collect_settled_day_masters(db_path=db)
        assert [r["prediction_id"] for r in settled] == [settled_id]
        assert open_id not in {r["prediction_id"] for r in settled}

    def test_keeps_unresolvable_rows_for_downstream_filtering(self, db):
        """unresolvable 行（resolution_rule='stale_no_market'）保留——状态级过滤属下游职责。"""
        pid = _insert(db)
        _settle(
            db,
            pid,
            status="unresolvable",
            resolved_at=None,
            excess_return=None,
            resolution_rule="stale_no_market",
        )
        settled = collect_settled_day_masters(db_path=db)
        assert [r["prediction_id"] for r in settled] == [pid]

    def test_reads_beyond_default_list_limit(self, db):
        """全量读取：行数超过 list_predictions 默认 limit=50 时不截断。"""
        for i in range(60):
            pid = _insert(db, symbol=f"60051{i % 10}.SH")
            _settle(db, pid)
        assert len(collect_settled_day_masters(db_path=db)) == 60

    def test_empty_db_returns_empty_list(self, db):
        """空库返回空列表，不抛异常。"""
        assert collect_settled_day_masters(db_path=db) == []
