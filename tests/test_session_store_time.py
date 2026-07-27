"""session_store 时间字段兜底回归测试。

对应 BUG #007：侧边栏会话时间显示 "Invalid Date"。
根因：历史脏数据 created_at 被错写为 'chat'/'analysis'，前端 new Date() 无法解析。
修复：后端 list_sessions 兜底 + init_db 迁移修复历史脏数据；前端 formatSessionTime 兜底。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from finance_agent import session_store


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """用临时数据库隔离，不污染真实 data/sessions.db。"""
    db_path = tmp_path / "test_sessions.db"
    monkeypatch.setattr(session_store, "_DB_PATH", db_path)
    session_store.init_db()
    return db_path


def _raw_insert(
    db_path: Path, session_id: str, created_at: str, session_type: str = "chat"
) -> None:
    """绕过 create_session，直接写入指定 created_at（用于构造脏数据）。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO sessions (session_id, display_name, created_at, session_type) "
        "VALUES (?, ?, ?, ?)",
        (session_id, f"test-{session_id}", created_at, session_type),
    )
    conn.commit()
    conn.close()


class TestCreatedAtNormalization:
    """list_sessions 必须对非法 created_at 兜底，前端永不收到 Invalid Date。"""

    def test_valid_iso_passthrough(self, tmp_db):
        """合法 ISO 时间戳应原样返回。"""
        _raw_insert(tmp_db, "valid-1", "2026-07-16T14:44:32.424729")
        sessions = session_store.list_sessions()
        assert sessions[0]["created_at"] == "2026-07-16T14:44:32.424729"

    def test_bad_value_chat_falls_back(self, tmp_db):
        """created_at='chat'（历史脏数据）应被兜底为可解析值。"""
        _raw_insert(tmp_db, "bad-1", "chat")
        sessions = session_store.list_sessions()
        ts = sessions[0]["created_at"]
        assert ts != "chat"
        # 兜底值必须能被 Date/fromisoformat 解析
        from datetime import datetime

        datetime.fromisoformat(ts)

    def test_bad_value_analysis_falls_back(self, tmp_db):
        """created_at='analysis'（历史脏数据）应被兜底。"""
        _raw_insert(tmp_db, "bad-2", "analysis")
        sessions = session_store.list_sessions()
        assert sessions[0]["created_at"] != "analysis"

    def test_empty_string_falls_back(self, tmp_db):
        """空字符串应被兜底。"""
        _raw_insert(tmp_db, "bad-3", "")
        sessions = session_store.list_sessions()
        assert sessions[0]["created_at"] != ""

    def test_new_chat_session_has_valid_timestamp(self, tmp_db):
        """新建 chat 会话 created_at 必须是合法 ISO 时间戳（当前代码不应再产生脏数据）。"""
        sid = session_store.create_chat_session("hello")
        sessions = [s for s in session_store.list_sessions() if s["session_id"] == sid]
        ts = sessions[0]["created_at"]
        from datetime import datetime

        datetime.fromisoformat(ts)  # 不抛异常即合法


class TestBadDataMigration:
    """init_db 迁移应修复历史脏数据。"""

    def test_migration_repairs_bad_values(self, tmp_db):
        """init_db 后，已存在的脏数据 created_at 应被改为 epoch 占位。"""
        _raw_insert(tmp_db, "dirty-1", "chat")
        _raw_insert(tmp_db, "dirty-2", "analysis")
        _raw_insert(tmp_db, "clean-1", "2026-07-15T10:00:00")

        # 再次 init_db 触发迁移
        session_store.init_db()

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        rows = {
            r["session_id"]: r["created_at"]
            for r in conn.execute("SELECT session_id, created_at FROM sessions")
        }
        conn.close()

        assert rows["dirty-1"] == "1970-01-01T00:00:00"
        assert rows["dirty-2"] == "1970-01-01T00:00:00"
        assert rows["clean-1"] == "2026-07-15T10:00:00"
