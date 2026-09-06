"""decision_log 存储(design 决策 1:与 session_store 同库 SQLite,幂等 DDL)。

旁路铁律:本模块任何失败由调用方(api.py 落库挂点 / outcome.job)try/except
兜底,不阻断业务。连接管理与 session_store 同款(WAL + busy_timeout 短连接),
但默认 DB 路径在调用期读取(不在 import 期),测试经 db_path 显式注入。
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DECISION_LOG_DDL = """
CREATE TABLE IF NOT EXISTS decision_log (
  decision_id    TEXT PRIMARY KEY,
  session_id     TEXT NOT NULL,
  langfuse_trace_id TEXT,
  timestamp      TEXT NOT NULL,
  ticker         TEXT NOT NULL,
  name           TEXT,
  action         TEXT NOT NULL,
  entry_price    REAL NOT NULL,
  stop_loss      REAL,
  target_price   REAL,
  confidence     REAL,
  position_size  REAL,
  status         TEXT NOT NULL DEFAULT 'open',
  settled_at     TEXT,
  settle_price   REAL,
  hold_days      INTEGER,
  decision_return REAL,
  benchmark_return REAL,
  decision_excess REAL,
  updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_log_status ON decision_log(status);
"""


def _default_db_path() -> Path:
    """默认与 session_store 同库;调用期读取(测试可 monkeypatch env)。"""
    return Path(os.getenv("SESSIONS_DB_PATH", "data/sessions.db"))


def _connect(db_path: str | Path | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_decision_log(db_path: str | Path | None = None) -> None:
    """幂等建表 + 索引(session_store 同款 CREATE IF NOT EXISTS 风格)。"""
    conn = _connect(db_path)
    try:
        conn.executescript(DECISION_LOG_DDL)
        conn.commit()
    finally:
        conn.close()


def insert_decision(record: dict[str, Any], db_path: str | Path | None = None) -> str:
    """插入 open 决策,返回 decision_id(未提供则生成 uuid)。"""
    decision_id = record.get("decision_id") or f"d_{uuid.uuid4().hex[:12]}"
    now = record.get("updated_at") or record["timestamp"]
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO decision_log (
                 decision_id, session_id, langfuse_trace_id, timestamp,
                 ticker, name, action, entry_price,
                 stop_loss, target_price, confidence, position_size,
                 status, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?)""",
            (
                decision_id,
                record["session_id"],
                record.get("langfuse_trace_id"),
                record["timestamp"],
                record["ticker"],
                record.get("name"),
                record["action"],
                record["entry_price"],
                record.get("stop_loss"),
                record.get("target_price"),
                record.get("confidence"),
                record.get("position_size"),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return decision_id


DECISION_STATUSES = ("open", "hit_stop", "hit_target", "expired")


def list_decisions(
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 200,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """只读:按 ticker/status 过滤的决策列表,按 timestamp 倒序。limit 钳制 1..1000。"""
    limit = max(1, min(int(limit), 1000))
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM decision_log"
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("ticker = ?")
            params.append(ticker)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def decision_stats(db_path: str | Path | None = None) -> dict[str, Any]:
    """只读:聚合战绩。胜率/均值只基于已结算(status!='open')记录,
    decision_excess 为 null 剔除出超额均值(不当作 0);无已结算时返回 null。"""
    conn = _connect(db_path)
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0])
        open_count = int(
            conn.execute("SELECT COUNT(*) FROM decision_log WHERE status='open'").fetchone()[0]
        )
        settled = total - open_count
        by_status = dict(
            conn.execute("SELECT status, COUNT(*) FROM decision_log GROUP BY status").fetchall()
        )
        win_rate: float | None = None
        avg_return: float | None = None
        avg_excess: float | None = None
        if settled:
            wins = int(
                conn.execute(
                    "SELECT COUNT(*) FROM decision_log WHERE status!='open' AND decision_return > 0"
                ).fetchone()[0]
            )
            win_rate = round(wins / settled, 4)
            avg_ret = conn.execute(
                "SELECT AVG(decision_return) FROM decision_log WHERE status!='open'"
            ).fetchone()[0]
            if avg_ret is not None:
                avg_return = round(float(avg_ret), 4)
            avg_exc = conn.execute(
                "SELECT AVG(decision_excess) FROM decision_log "
                "WHERE status!='open' AND decision_excess IS NOT NULL"
            ).fetchone()[0]
            if avg_exc is not None:
                avg_excess = round(float(avg_exc), 4)
        return {
            "total": total,
            "open": open_count,
            "settled": settled,
            "by_status": by_status,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "avg_excess": avg_excess,
        }
    finally:
        conn.close()


def get_open_decisions(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """所有 status='open' 决策(结算 job 的输入)。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM decision_log WHERE status='open'").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_settled(
    decision_id: str, settled: dict[str, Any], db_path: str | Path | None = None
) -> None:
    """写入结算结果。幂等由调用方保证(settled_at IS NULL 才调)。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            """UPDATE decision_log SET
                 status=?, settled_at=?, settle_price=?, hold_days=?,
                 decision_return=?, benchmark_return=?, decision_excess=?,
                 updated_at=?
               WHERE decision_id=?""",
            (
                settled["status"],
                settled["settled_at"],
                settled["settle_price"],
                settled["hold_days"],
                settled["decision_return"],
                settled.get("benchmark_return"),
                settled.get("decision_excess"),
                settled["settled_at"],
                decision_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
