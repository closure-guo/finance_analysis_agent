"""SQLite session store — 永久存储分析会话。

会话 = 一次股票深度分析 + 后续追问。
SQLite 单文件，WAL 模式，永久保留直到用户手动删除。
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_DB_PATH = Path("data/sessions.db")

_DB_PATH.parent.mkdir(exist_ok=True)


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize sessions table."""
    conn = _get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id   TEXT PRIMARY KEY,
            stock_code   TEXT NOT NULL,
            stock_name   TEXT NOT NULL,
            display_name TEXT,
            status       TEXT DEFAULT 'completed',
            report_markdown  TEXT,
            chart_data       TEXT,
            analyst_reports  TEXT,
            agent_process    TEXT,
            analyst_summaries TEXT,
            chat_history     TEXT DEFAULT '[]',
            created_at   TEXT NOT NULL,
            duration_ms  INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def create_session(
    stock_code: str,
    stock_name: str,
    report_markdown: str = "",
    chart_data: dict | None = None,
    analyst_reports: dict | None = None,
    agent_process: dict | None = None,
    analyst_summaries: dict | None = None,
    duration_ms: int = 0,
) -> str:
    """Create a new session record, return session_id."""
    session_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    display_name = f"{stock_name} {datetime.now().strftime('%m-%d %H:%M')}"

    conn = _get_db()
    conn.execute(
        """
        INSERT INTO sessions
            (session_id, stock_code, stock_name, display_name, status,
             report_markdown, chart_data, analyst_reports, agent_process,
             analyst_summaries, chat_history, created_at, duration_ms)
        VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, '[]', ?, ?)
        """,
        (
            session_id,
            stock_code,
            stock_name,
            display_name,
            report_markdown,
            json.dumps(chart_data or {}, ensure_ascii=False),
            json.dumps(analyst_reports or {}, ensure_ascii=False, default=str),
            json.dumps(agent_process or {}, ensure_ascii=False, default=str),
            json.dumps(analyst_summaries or {}, ensure_ascii=False, default=str),
            now,
            duration_ms,
        ),
    )
    conn.commit()
    conn.close()
    return session_id


def list_sessions() -> list[dict[str, Any]]:
    """List all sessions (metadata only, no report body)."""
    conn = _get_db()
    rows = conn.execute(
        """
        SELECT session_id, stock_code, stock_name, display_name, status,
               created_at, duration_ms,
               length(report_markdown) as report_len
        FROM sessions
        ORDER BY created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    """Get full session by id."""
    conn = _get_db()
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for key in (
        "chart_data",
        "analyst_reports",
        "agent_process",
        "analyst_summaries",
        "chat_history",
    ):
        if d.get(key):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d[key] = json.loads(d[key])
    return d


def rename_session(session_id: str, display_name: str) -> bool:
    """Rename a session's display name."""
    conn = _get_db()
    cur = conn.execute(
        "UPDATE sessions SET display_name = ? WHERE session_id = ?",
        (display_name, session_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_session(session_id: str) -> bool:
    """Delete a session."""
    conn = _get_db()
    cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def append_chat(session_id: str, role: str, content: str) -> None:
    """Append a chat message to session's chat_history."""
    conn = _get_db()
    row = conn.execute(
        "SELECT chat_history FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        conn.close()
        return
    try:
        history = json.loads(row["chat_history"]) if row["chat_history"] else []
    except (json.JSONDecodeError, TypeError):
        history = []
    history.append({"role": role, "content": content, "ts": datetime.now().isoformat()})
    conn.execute(
        "UPDATE sessions SET chat_history = ? WHERE session_id = ?",
        (json.dumps(history, ensure_ascii=False), session_id),
    )
    conn.commit()
    conn.close()
