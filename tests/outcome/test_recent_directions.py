"""TDD: add-decision-hysteresis T1——近窗历史决策只读查询（滞回数据源）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from finance_agent.outcome.track_record import model as track_model


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "t.db"
    track_model.init_predictions(db_path=path)
    return path


def _insert(symbol: str, direction: str, conf: float, created: str, db) -> None:
    track_model.insert_prediction(
        {
            "source_type": "live",
            "symbol": symbol,
            "direction": direction,
            "confidence": conf,
            "created_at": created,
        },
        db_path=db,
    )


class TestRecentDirections:
    def test_returns_window_sequence_ascending(self, db):
        _insert("688072.SH", "short", 0.55, "2026-09-28T10:00:00", db)
        _insert("688072.SH", "neutral", 0.60, "2026-10-01T10:00:00", db)
        _insert("688072.SH", "long", 0.50, "2026-10-02T10:00:00", db)
        seq = track_model.recent_directions("688072", window_days=5, db_path=db, today="2026-10-02")
        assert [(x["direction"], x["confidence"]) for x in seq] == [
            ("short", 0.55),
            ("neutral", 0.60),
            ("long", 0.50),
        ]
        assert seq[-1]["date"] == "2026-10-02"

    def test_symbol_suffix_mapping(self, db):
        _insert("688072.SH", "short", 0.55, "2026-10-01T10:00:00", db)
        _insert("000001.SZ", "long", 0.55, "2026-10-01T10:00:00", db)
        assert len(track_model.recent_directions("688072", db_path=db, today="2026-10-02")) == 1
        assert len(track_model.recent_directions("000001", db_path=db, today="2026-10-02")) == 1

    def test_window_excludes_old_entries(self, db):
        _insert("688072.SH", "short", 0.55, "2026-09-20T10:00:00", db)  # 窗口外
        _insert("688072.SH", "neutral", 0.60, "2026-10-01T10:00:00", db)
        seq = track_model.recent_directions("688072", window_days=5, db_path=db, today="2026-10-02")
        assert [x["direction"] for x in seq] == ["neutral"]

    def test_empty_db_returns_empty_list(self, db):
        assert track_model.recent_directions("688072", db_path=db, today="2026-10-02") == []

    def test_fail_open_on_db_error(self, tmp_path):
        # 只读查询 fail-open：DB 异常返回 []（滞回不生效），MUST NOT 炸管线
        bad = tmp_path / "bad.db"
        bad.write_text("not a db", encoding="utf-8")
        assert track_model.recent_directions("688072", db_path=bad, today="2026-10-02") == []
