"""predictions 数据模型(add-track-record):append-only + 冻结字段守卫 + decision_log 迁移。

与 outcome/store.py 同款 SQLite(WAL + busy_timeout 短连接),db_path 调用期注入。
冻结铁律:方向/入场价/快照/创建时间写入后不可改;判定结果只经 update_prediction_status
更新 status/resolved_at/exit_price/raw_return/excess_return/resolution_rule。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

PREDICTIONS_DDL = """
CREATE TABLE IF NOT EXISTS predictions (
  prediction_id     TEXT PRIMARY KEY,
  source_type       TEXT NOT NULL CHECK (source_type IN ('backtest','live')),
  symbol            TEXT NOT NULL,
  symbol_name       TEXT,
  direction         TEXT NOT NULL CHECK (direction IN ('long','short','neutral')),
  entry_price       REAL NOT NULL,
  target_price      REAL,
  horizon_days      INTEGER NOT NULL DEFAULT 252,
  confidence        REAL CHECK (confidence BETWEEN 0 AND 1),
  benchmark         TEXT NOT NULL DEFAULT '000300.SH',
  rationale_snapshot TEXT NOT NULL,
  langfuse_trace_id TEXT,
  status            TEXT NOT NULL DEFAULT 'open',
  created_at        TEXT NOT NULL,
  resolved_at       TEXT,
  exit_price        REAL,
  raw_return        REAL,
  excess_return     REAL,
  resolution_rule   TEXT,
  updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);
"""

PREDICTIONS_STATUSES = ("open", "resolved_win", "resolved_loss", "resolved_neutral", "unresolvable")
_FROZEN_FIELDS = (
    "direction",
    "entry_price",
    "target_price",
    "rationale_snapshot",
    "created_at",
    "source_type",
    "symbol",
)
_MUTABLE_FIELDS = (
    "status",
    "resolved_at",
    "exit_price",
    "raw_return",
    "excess_return",
    "resolution_rule",
    "updated_at",
)


class FrozenFieldError(Exception):
    """尝试修改冻结字段(append-only 铁律)。"""


def _default_db_path() -> Path:
    return Path(os.getenv("SESSIONS_DB_PATH", "data/sessions.db"))


def _connect(db_path: str | Path | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_predictions(db_path: str | Path | None = None) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(PREDICTIONS_DDL)
        conn.commit()
    finally:
        conn.close()


def insert_prediction(record: dict[str, Any], db_path: str | Path | None = None) -> str:
    """插入一条观点;created_at 服务端生成;快照 JSON 序列化后冻结。"""
    prediction_id = record.get("prediction_id") or f"p_{uuid.uuid4().hex[:12]}"
    created_at = record.get("created_at") or record.get("timestamp") or datetime.now().isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO predictions (
                 prediction_id, source_type, symbol, symbol_name, direction,
                 entry_price, target_price, horizon_days, confidence, benchmark,
                 rationale_snapshot, langfuse_trace_id, status, created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?, ?)""",
            (
                prediction_id,
                record["source_type"],
                record["symbol"],
                record.get("symbol_name"),
                record["direction"],
                record["entry_price"],
                record.get("target_price"),
                int(record.get("horizon_days", 252)),
                record.get("confidence"),
                record.get("benchmark", "000300.SH"),
                json.dumps(record.get("rationale_snapshot") or {}, ensure_ascii=False),
                record.get("langfuse_trace_id"),
                created_at,
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return prediction_id


def update_prediction_status(
    prediction_id: str, resolved: dict[str, Any], db_path: str | Path | None = None
) -> None:
    """判定结果更新。尝试改冻结字段抛 FrozenFieldError;幂等由调用方保证。"""
    frozen_hits = [f for f in _FROZEN_FIELDS if f in resolved]
    if frozen_hits:
        raise FrozenFieldError(f"attempt to mutate frozen field(s): {frozen_hits}")
    conn = _connect(db_path)
    try:
        cur = conn.execute("SELECT * FROM predictions WHERE prediction_id=?", (prediction_id,))
        if cur.fetchone() is None:
            return
        fields = [f for f in _MUTABLE_FIELDS if f in resolved]
        if not fields:
            return
        sets = ", ".join(f"{f}=?" for f in fields)
        params = [resolved[f] for f in fields]
        # 列名来自固定常量元组 _MUTABLE_FIELDS，值已参数化
        sql = f"UPDATE predictions SET {sets} WHERE prediction_id=?"  # noqa: S608
        conn.execute(sql, (*params, prediction_id))
        conn.commit()
    finally:
        conn.close()


def list_predictions(
    ticker: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM predictions"
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("symbol LIKE ?")
            params.append(f"%{ticker}%")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def prediction_stats(
    source_type: str | None = None, db_path: str | Path | None = None
) -> dict[str, Any]:
    """胜率/超额聚合。胜率只基于 resolved_win/resolved_loss;neutral/unresolvable 不进分母。"""
    conn = _connect(db_path)
    try:
        where, params = (" WHERE source_type=?", [source_type]) if source_type else ("", [])
        src_cond = " AND source_type=?" if source_type else ""
        # where/src_cond 均为固定字面量，值已参数化
        q_total = f"SELECT COUNT(*) FROM predictions{where}"  # noqa: S608
        q_open = f"SELECT COUNT(*) FROM predictions WHERE status='open'{src_cond}"  # noqa: S608
        q_win = f"SELECT COUNT(*) FROM predictions WHERE status='resolved_win'{src_cond}"  # noqa: S608
        q_loss = f"SELECT COUNT(*) FROM predictions WHERE status='resolved_loss'{src_cond}"  # noqa: S608
        q_avg = f"SELECT AVG(excess_return) FROM predictions WHERE status IN ('resolved_win','resolved_loss'){src_cond}"  # noqa: S608
        q_counts = f"SELECT status, COUNT(*) FROM predictions{where} GROUP BY status"  # noqa: S608
        total = int(conn.execute(q_total, params).fetchone()[0])
        open_count = int(conn.execute(q_open, params).fetchone()[0])
        wins = int(conn.execute(q_win, params).fetchone()[0])
        losses = int(conn.execute(q_loss, params).fetchone()[0])
        settled = wins + losses
        win_rate = round(wins / settled, 4) if settled else None
        avg_exc = conn.execute(q_avg, params).fetchone()[0]
        avg_excess = round(float(avg_exc), 4) if avg_exc is not None else None
        return {
            "total": total,
            "open": open_count,
            "settled": settled,
            "win_rate": win_rate,
            "avg_excess": avg_excess,
            "status_counts": dict(conn.execute(q_counts, params).fetchall()),
        }
    finally:
        conn.close()


def migrate_decision_log(db_path: str | Path | None = None) -> int:
    """一次性迁移 decision_log → predictions(方向映射 + 最小快照)。幂等:重复执行跳过已迁移。

    首迁时给 decision_log 加 prediction_id_migrated 列作为迁移标记;之后重复执行只迁未迁移行。
    """
    conn = _connect(db_path)
    migrated = 0
    try:
        try:
            rows = conn.execute(
                "SELECT * FROM decision_log WHERE prediction_id_migrated IS NULL"
            ).fetchall()
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE decision_log ADD COLUMN prediction_id_migrated TEXT")
            conn.commit()
            rows = conn.execute(
                "SELECT * FROM decision_log WHERE prediction_id_migrated IS NULL"
            ).fetchall()
        for r in rows:
            action = r["action"]
            direction = "long" if action == "buy" else ("short" if action == "sell" else "neutral")
            pid = f"p_{uuid.uuid4().hex[:12]}"
            snapshot = json.dumps(
                {
                    "migrated_from": "decision_log",
                    "decision_id": r["decision_id"],
                    "action": action,
                },
                ensure_ascii=False,
            )
            conn.execute(
                """INSERT INTO predictions (
                     prediction_id, source_type, symbol, symbol_name, direction,
                     entry_price, target_price, confidence, benchmark,
                     rationale_snapshot, langfuse_trace_id, status, created_at, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'open', ?, ?)""",
                (
                    pid,
                    "live",
                    f"{r['ticker']}.SH"
                    if str(r["ticker"]).startswith("6")
                    else f"{r['ticker']}.SZ",
                    r["name"],
                    direction,
                    float(r["entry_price"]),
                    r["target_price"],
                    r["confidence"],
                    "000300.SH",
                    snapshot,
                    r["langfuse_trace_id"],
                    r["timestamp"],
                    r["timestamp"],
                ),
            )
            conn.execute(
                "UPDATE decision_log SET prediction_id_migrated=? WHERE decision_id=?",
                (pid, r["decision_id"]),
            )
            migrated += 1
        conn.commit()
    finally:
        conn.close()
    return migrated
