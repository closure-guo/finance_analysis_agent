"""add-index-performance-compare:指数收盘存储、日批同步、区间收益读数单测。"""

import pandas as pd
import pytest

from finance_agent.outcome.track_record.index_compare import (
    INDEX_COMPARE_UNIVERSE,
    sync_index_closes,
)
from finance_agent.outcome.track_record.model import (
    init_track_record_tables,
    list_index_closes,
    upsert_index_closes,
)


@pytest.fixture()
def db(tmp_path):
    db = tmp_path / "t.db"
    init_track_record_tables(db)
    return db


class TestIndexClosesStorage:
    def test_upsert_and_list(self, db):
        n = upsert_index_closes(
            [("000300", "2026-09-28", 4000.0), ("000300", "2026-09-29", 4040.0)], db_path=db
        )
        assert n == 2
        rows = list_index_closes("000300", db_path=db)
        assert [r["trade_date"] for r in rows] == ["2026-09-28", "2026-09-29"]
        assert rows[0]["close"] == pytest.approx(4000.0)

    def test_idempotent_replace(self, db):
        upsert_index_closes([("000300", "2026-09-28", 4000.0)], db_path=db)
        upsert_index_closes([("000300", "2026-09-28", 4010.0)], db_path=db)
        rows = list_index_closes("000300", db_path=db)
        assert len(rows) == 1 and rows[0]["close"] == pytest.approx(4010.0)

    def test_list_end_boundary_inclusive_and_empty(self, db):
        upsert_index_closes(
            [("000905", "2026-09-28", 6000.0), ("000905", "2026-10-09", 6600.0)], db_path=db
        )
        assert (
            list_index_closes("000905", end="2026-09-28", db_path=db)[0]["trade_date"]
            == "2026-09-28"
        )
        assert list_index_closes("000852", db_path=db) == []
        assert list_index_closes("000905", end="2026-01-01", db_path=db) == []


def _fake_client(
    closes_by_code: dict[str, list[tuple[str, float]]], fail_codes: set[str] | None = None
):
    """构造 AKShareClient 替身:fetch_index_kline 返回中文列名 DataFrame,失败码抛异常。"""
    fail_codes = fail_codes or set()

    class _C:
        def fetch_index_kline(self, index_code: str, days: int = 250):
            if index_code in fail_codes:
                raise RuntimeError(f"rate limited: {index_code}")
            rows = closes_by_code.get(index_code, [])
            return pd.DataFrame({"日期": [d for d, _ in rows], "收盘": [c for _, c in rows]})

    return _C()


class TestSyncIndexCloses:
    def test_universe_has_five_major_indices(self):
        assert [u["code"] for u in INDEX_COMPARE_UNIVERSE] == [
            "000001",
            "000300",
            "000905",
            "000852",
            "399006",
        ]
        assert all(u["name"] for u in INDEX_COMPARE_UNIVERSE)

    def test_sync_stores_all_and_reports_count(self, db):
        client = _fake_client(
            {
                "000300": [("2026-09-28", 4000.0), ("2026-09-29", 4040.0)],
                "000001": [("2026-09-28", 3000.0)],
            }
        )
        result = sync_index_closes(client=client, db_path=db)
        assert result["stored"] == 3 and result["failed"] == []
        assert len(list_index_closes("000300", db_path=db)) == 2

    def test_sync_single_failure_isolated(self, db):
        client = _fake_client({"000300": [("2026-09-28", 4000.0)]}, fail_codes={"000905", "399006"})
        result = sync_index_closes(client=client, db_path=db)
        assert result["failed"] == ["000905", "399006"]
        assert result["stored"] >= 1  # 其余指数照常落库
        assert len(list_index_closes("000300", db_path=db)) == 1
