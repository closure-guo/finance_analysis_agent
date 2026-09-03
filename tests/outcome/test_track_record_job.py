"""add-track-record Task 3:predictions 日批判定 job(settle_open_predictions)。"""

import datetime

import pandas as pd

from finance_agent.outcome.track_record.job import settle_open_predictions
from finance_agent.outcome.track_record.model import (
    init_predictions,
    insert_prediction,
    list_predictions,
)


def _db(tmp_path):
    db = tmp_path / "t.db"
    init_predictions(db)
    return db


def _kline(prices, start="2026-09-02"):
    return pd.DataFrame(
        {
            "日期": [
                str(datetime.date.fromisoformat(start) + datetime.timedelta(days=i))
                for i in range(len(prices))
            ],
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "收盘": prices,
            "成交量": [1] * len(prices),
        }
    )


class _StubClient:
    def __init__(self, klines, benchmark=None):
        self.klines = klines
        self.benchmark = benchmark

    def fetch_kline(self, code, days=None):
        return self.klines.get(code)

    def fetch_index_kline(self, code, days=None):
        return self.benchmark


def _insert(
    db, symbol="600519.SH", entry=100.0, horizon=10, direction="long", created="2026-09-01T10:00:00"
):
    return insert_prediction(
        {
            "source_type": "live",
            "symbol": symbol,
            "symbol_name": "贵州茅台",
            "direction": direction,
            "entry_price": entry,
            "horizon_days": horizon,
            "confidence": 0.8,
            "rationale_snapshot": {"action": "buy"},
            "created_at": created,
        },
        db_path=db,
    )


def test_settle_horizon_win(tmp_path):
    db = _db(tmp_path)
    pid = _insert(db)
    client = _StubClient({"600519": _kline([101, 102, 103, 104, 105, 106, 107, 108, 109, 115])})
    result = settle_open_predictions(client=client, db_path=db)
    assert result["settled"] == 1 and result["errors"] == 0
    row = list_predictions(db_path=db)[0]
    assert row["status"] == "resolved_win"
    assert row["prediction_id"] == pid


def test_settle_skips_not_enough_rows(tmp_path):
    db = _db(tmp_path)
    _insert(db)
    client = _StubClient({"600519": _kline([101, 102])})  # 2 行 < horizon 10
    result = settle_open_predictions(client=client, db_path=db)
    assert result["settled"] == 0 and result["skipped"] == 1
    assert list_predictions(db_path=db)[0]["status"] == "open"


def test_superseded_resolves_old(tmp_path):
    db = _db(tmp_path)
    old = _insert(db, direction="long", created="2026-09-01T10:00:00")
    _insert(db, direction="short", created="2026-09-03T10:00:00")  # 反向 → 旧观点被 supersede
    client = _StubClient({"600519": _kline([100, 99, 98, 97])})
    result = settle_open_predictions(client=client, db_path=db)
    assert result["superseded"] == 1
    rows = {r["prediction_id"]: r for r in list_predictions(db_path=db)}
    assert rows[old]["status"] in ("resolved_win", "resolved_loss", "resolved_neutral")
    assert rows[old]["resolution_rule"] == "superseded"


def test_stale_marks_unresolvable(tmp_path):
    db = _db(tmp_path)
    _insert(db, created="2026-09-01T10:00:00")
    # ticker 行情停在 9-01,基准已到 9-10(落后 > STALE_DAYS)
    client = _StubClient(
        {"600519": _kline([100], start="2026-09-01")},
        benchmark=_kline(
            [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110], start="2026-09-02"
        ),
    )
    result = settle_open_predictions(client=client, db_path=db)
    assert result["unresolvable"] == 1
    assert list_predictions(db_path=db)[0]["status"] == "unresolvable"
