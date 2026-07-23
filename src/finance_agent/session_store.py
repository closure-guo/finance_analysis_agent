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

# created_at 列曾被旧版代码错写为 session_type 的值（'chat' / 'analysis'），
# 这些值无法被 Date 解析，前端显示 "Invalid Date"。这里集中兜底。
_BAD_CREATED_AT_VALUES = {"chat", "analysis", "deep", "quick", ""}


def _is_valid_iso(ts: str | None) -> bool:
    """判断 created_at 是否为可被前端 Date 解析的合法时间字符串。"""
    if not ts or not isinstance(ts, str):
        return False
    if ts in _BAD_CREATED_AT_VALUES:
        return False
    try:
        datetime.fromisoformat(ts)
        return True
    except ValueError:
        return False


def _normalize_created_at(ts: str | None) -> str:
    """返回可安全交给前端 Date 的 created_at；非法值回退为 epoch。"""
    if _is_valid_iso(ts):
        return ts  # type: ignore[return-value]
    # 无法还原原始时间，用 epoch 兜底（前端可识别并显示"未知时间"）
    return "1970-01-01T00:00:00"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize sessions table and migrate schema."""
    conn = _get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id   TEXT PRIMARY KEY,
            stock_code   TEXT,
            stock_name   TEXT,
            display_name TEXT,
            status       TEXT DEFAULT 'completed',
            focus        TEXT DEFAULT '',
            pending_intent TEXT DEFAULT '',
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
    # 迁移：为旧表添加缺失列
    for _col, ddl in [
        ("session_type", "ALTER TABLE sessions ADD COLUMN session_type TEXT DEFAULT 'analysis'"),
        ("focus", "ALTER TABLE sessions ADD COLUMN focus TEXT DEFAULT ''"),
        ("pending_intent", "ALTER TABLE sessions ADD COLUMN pending_intent TEXT DEFAULT ''"),
    ]:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(ddl)

    # 迁移：旧表的 stock_code / stock_name 可能为 NOT NULL；SQLite 不支持 ALTER COLUMN，需要重建表
    _relax_stock_columns(conn)

    # 迁移：修复历史脏数据——created_at 被旧版代码错写为 session_type 值（'chat'/'analysis'）。
    # 无法还原真实时间，回退为 epoch 占位（前端识别为"未知时间"，不再显示 Invalid Date）。
    _repair_bad_created_at(conn)

    # 迁移：清理 epoch 占位的脏数据会话。这些会话原始时间已永久丢失，
    # 保留只会显示"未知时间"且排序错乱（ORDER BY created_at DESC 把它们堆在末尾）。
    # 启动时幂等删除。必须在 _repair_bad_created_at 之后执行。
    _purge_epoch_sessions(conn)

    conn.commit()
    conn.close()


def _repair_bad_created_at(conn: sqlite3.Connection) -> None:
    """把 created_at 列中的非法值（'chat'/'analysis' 等）回退为 epoch 占位。"""
    placeholders = ",".join("?" for _ in _BAD_CREATED_AT_VALUES)
    conn.execute(
        f"UPDATE sessions SET created_at = '1970-01-01T00:00:00' "  # noqa: S608 - 列名/表名均为代码内常量，值已参数化
        f"WHERE created_at IN ({placeholders})",
        tuple(_BAD_CREATED_AT_VALUES),
    )


def _purge_epoch_sessions(conn: sqlite3.Connection) -> None:
    """删除 created_at 为 epoch 占位的脏数据会话。

    这些会话的原始时间已永久丢失（旧版代码列错位写入），保留只会显示"未知时间"
    且排序错乱。启动时幂等清理。必须在 _repair_bad_created_at 之后执行。
    """
    conn.execute("DELETE FROM sessions WHERE created_at = '1970-01-01T00:00:00'")


def _relax_stock_columns(conn: sqlite3.Connection) -> None:
    """如果 stock_code 或 stock_name 仍带 NOT NULL 约束，则重建表以移除约束。"""
    # PRAGMA table_info 返回列：cid, name, type, notnull, dflt_value, pk
    cols = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(sessions)")}
    if cols.get("stock_code") == 1 or cols.get("stock_name") == 1:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions_new (
                session_id   TEXT PRIMARY KEY,
                stock_code   TEXT,
                stock_name   TEXT,
                display_name TEXT,
                status       TEXT DEFAULT 'completed',
                focus        TEXT DEFAULT '',
                pending_intent TEXT DEFAULT '',
                report_markdown  TEXT,
                chart_data       TEXT,
                analyst_reports  TEXT,
                agent_process    TEXT,
                analyst_summaries TEXT,
                chat_history     TEXT DEFAULT '[]',
                created_at   TEXT NOT NULL,
                duration_ms  INTEGER DEFAULT 0,
                session_type TEXT DEFAULT 'analysis'
            )
            """
        )
        conn.execute("INSERT INTO sessions_new SELECT * FROM sessions")
        conn.execute("DROP TABLE sessions")
        conn.execute("ALTER TABLE sessions_new RENAME TO sessions")


def create_session(
    stock_code: str = "",
    stock_name: str = "",
    report_markdown: str = "",
    chart_data: dict | None = None,
    analyst_reports: dict | None = None,
    agent_process: dict | None = None,
    analyst_summaries: dict | None = None,
    duration_ms: int = 0,
    session_type: str = "analysis",
    display_name: str | None = None,
    status: str = "completed",
) -> str:
    """Create a new session record, return session_id."""
    session_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    if display_name is None:
        display_name = f"{stock_name} {datetime.now().strftime('%m-%d %H:%M')}"

    conn = _get_db()
    conn.execute(
        """
        INSERT INTO sessions
            (session_id, stock_code, stock_name, display_name, status,
             report_markdown, chart_data, analyst_reports, agent_process,
             analyst_summaries, chat_history, created_at, duration_ms, session_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
        """,
        (
            session_id,
            stock_code,
            stock_name,
            display_name,
            status,
            report_markdown,
            json.dumps(chart_data or {}, ensure_ascii=False),
            json.dumps(analyst_reports or {}, ensure_ascii=False, default=str),
            json.dumps(agent_process or {}, ensure_ascii=False, default=str),
            json.dumps(analyst_summaries or {}, ensure_ascii=False, default=str),
            now,
            duration_ms,
            session_type,
        ),
    )
    conn.commit()
    conn.close()
    return session_id


def update_session_for_clarify(
    session_id: str,
    stock_code: str | None = None,
    stock_name: str | None = None,
    display_name: str | None = None,
    focus: str | None = None,
    pending_intent: str | None = None,
    status: str | None = None,
) -> bool:
    """更新澄清阶段的 session 字段。"""
    updates = []
    values = []
    if stock_code is not None:
        updates.append("stock_code = ?")
        values.append(stock_code)
    if stock_name is not None:
        updates.append("stock_name = ?")
        values.append(stock_name)
    if display_name is not None:
        updates.append("display_name = ?")
        values.append(display_name)
    if focus is not None:
        updates.append("focus = ?")
        values.append(focus)
    if pending_intent is not None:
        updates.append("pending_intent = ?")
        values.append(pending_intent)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if not updates:
        return True

    conn = _get_db()
    cur = conn.execute(
        f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",  # noqa: S608
        (*values, session_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def update_session_report(
    session_id: str,
    report_markdown: str = "",
    chart_data: dict | None = None,
    analyst_reports: dict | None = None,
    agent_process: dict | None = None,
    analyst_summaries: dict | None = None,
    duration_ms: int = 0,
    status: str = "completed",
) -> bool:
    """更新 session 的报告数据和状态。

    用于管线启动时先创建 running session，完成后再回填报告。
    """
    conn = _get_db()
    cur = conn.execute(
        """
        UPDATE sessions SET
            report_markdown = ?,
            chart_data = ?,
            analyst_reports = ?,
            agent_process = ?,
            analyst_summaries = ?,
            duration_ms = ?,
            status = ?
        WHERE session_id = ?
        """,
        (
            report_markdown,
            json.dumps(chart_data or {}, ensure_ascii=False),
            json.dumps(analyst_reports or {}, ensure_ascii=False, default=str),
            json.dumps(agent_process or {}, ensure_ascii=False, default=str),
            json.dumps(analyst_summaries or {}, ensure_ascii=False, default=str),
            duration_ms,
            status,
            session_id,
        ),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def update_session_status(session_id: str, status: str) -> bool:
    """更新 session 状态（如 running -> failed）。"""
    conn = _get_db()
    cur = conn.execute(
        "UPDATE sessions SET status = ? WHERE session_id = ?",
        (status, session_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def create_chat_session(display_name: str) -> str:
    """创建快速模式对话 session，返回 session_id。

    快速模式无股票代码/报告，仅记录 chat_history。
    display_name 通常为用户问题摘要。
    """
    return create_session(
        stock_code="",
        stock_name="",
        display_name=display_name,
        session_type="chat",
    )


def list_sessions() -> list[dict[str, Any]]:
    """List all sessions (metadata only, no report body)."""
    conn = _get_db()
    rows = conn.execute(
        """
        SELECT session_id, stock_code, stock_name, display_name, status,
               focus, pending_intent, created_at, duration_ms, session_type,
               length(report_markdown) as report_len
        FROM sessions
        ORDER BY created_at DESC
        """
    ).fetchall()
    conn.close()
    # 防御性兜底：即便迁移漏网或外部写入脏数据，前端也拿不到非法 created_at
    result = []
    for r in rows:
        d = dict(r)
        d["created_at"] = _normalize_created_at(d.get("created_at"))
        result.append(d)
    return result


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


def append_chat(
    session_id: str,
    role: str,
    content: str,
    thinking: str | None = None,
    tool_calls: list | None = None,
) -> None:
    """Append a chat message to session's chat_history.

    Args:
        session_id: 会话 ID
        role: 消息角色（user/assistant）
        content: 最终回复文本
        thinking: 可选的 agent 思考过程原文（用于历史会话回显）
        tool_calls: 可选的工具调用记录列表（含 name/args/result_text/done）
    """
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
    entry: dict = {"role": role, "content": content, "ts": datetime.now().isoformat()}
    if thinking:
        entry["thinking"] = thinking
    if tool_calls:
        entry["tool_calls"] = tool_calls
    history.append(entry)
    conn.execute(
        "UPDATE sessions SET chat_history = ? WHERE session_id = ?",
        (json.dumps(history, ensure_ascii=False), session_id),
    )
    conn.commit()
    conn.close()
