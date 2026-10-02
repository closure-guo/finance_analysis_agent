"""add-index-performance-compare:指数收盘存储、日批同步、区间收益读数单测。"""

import pandas as pd
import pytest

from finance_agent.outcome.track_record.index_compare import (
    INDEX_COMPARE_UNIVERSE,
    sync_index_closes,
)
from finance_agent.outcome.track_record.marking import run_daily_marking
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
                "000905": [("2026-09-28", 6000.0)],
                "000852": [("2026-09-28", 2500.0)],
                "399006": [("2026-09-28", 2000.0)],
            }
        )
        result = sync_index_closes(client=client, db_path=db)
        assert result["stored"] == 6 and result["failed"] == []
        assert len(list_index_closes("000300", db_path=db)) == 2

    def test_sync_single_failure_isolated(self, db):
        client = _fake_client(
            {
                "000300": [("2026-09-28", 4000.0)],
                "000001": [("2026-09-28", 3000.0)],
                "000852": [("2026-09-28", 2500.0)],
            },
            fail_codes={"000905", "399006"},
        )
        result = sync_index_closes(client=client, db_path=db)
        assert result["failed"] == ["000905", "399006"]
        assert result["stored"] >= 3  # 其余指数照常落库
        assert len(list_index_closes("000300", db_path=db)) == 1

    def test_sync_truncates_datetime64_dates(self, db):
        """新浪回退源返回 datetime64 日期;落库必须截断到 YYYY-MM-DD(Fix review finding)。"""
        df_dates = pd.DataFrame(
            {"日期": pd.to_datetime(["2026-09-28", "2026-09-29"]), "收盘": [4000.0, 4040.0]}
        )

        class _TsClient:
            def fetch_index_kline(self, index_code: str, days: int = 250):
                return df_dates if index_code == "000300" else pd.DataFrame()

        result = sync_index_closes(client=_TsClient(), db_path=db)
        assert result["failed"] == [
            "000001",
            "000905",
            "000852",
            "399006",
        ]  # 空行情=失败(修正后语义)
        rows = list_index_closes("000300", db_path=db)
        assert [r["trade_date"] for r in rows] == ["2026-09-28", "2026-09-29"]


class TestDailyMarkingIndexSync:
    def _seed_open_prediction(self, db):
        from finance_agent.outcome.track_record.model import insert_prediction

        insert_prediction(
            {
                "source_type": "live",
                "symbol": "600519.SH",
                "symbol_name": "贵州茅台",
                "direction": "long",
                "entry_price": 100.0,
                "horizon_days": 20,
                "confidence": 0.8,
                "rationale_snapshot": {"action": "buy"},
                "created_at": "2026-09-01T10:00:00",
            },
            db_path=db,
        )

    def test_marking_summary_has_index_keys_and_stores(self, db):
        self._seed_open_prediction(db)
        # 需给全宇宙 5 个指数都喂数据:空行情=失败(Task 2 定案语义),
        # 否则 index_failed 断言与「全部成功」的测试意图相悖
        client = _fake_client({u["code"]: [("2026-09-28", 4000.0)] for u in INDEX_COMPARE_UNIVERSE})
        result = run_daily_marking(client=client, db_path=db, kline_days=5)
        assert result["index_stored"] >= 1
        assert result["index_failed"] == []
        # 盯市三键不受指数落库影响(errors 仍为盯市自身口径)
        assert set(result) >= {"marked", "skipped", "errors", "index_stored", "index_failed"}

    def test_marking_index_sync_all_failed_still_ok(self, db):
        self._seed_open_prediction(db)
        client = _fake_client({}, fail_codes={u["code"] for u in INDEX_COMPARE_UNIVERSE})
        result = run_daily_marking(client=client, db_path=db, kline_days=5)
        assert result["index_stored"] == 0
        assert len(result["index_failed"]) == 5
        # 盯市主链路照常返回(不抛错、无额外 errors)
        assert "metrics_date" in result
