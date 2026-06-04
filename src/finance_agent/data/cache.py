"""SQLite 缓存读写 + TTL 过期。

接口：
- get(key) → data | None
- set(key, data, ttl_seconds=None, expire_at=None)
- delete(key)
- keys() → list[str]

data 支持 dict 和 pd.DataFrame，内部序列化为 JSON/Parquet 存入 SQLite。
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

import pandas as pd


class DataCache:
    def __init__(self, db_path: str = "cache.db"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                data_type TEXT NOT NULL DEFAULT 'json',
                data BLOB NOT NULL,
                expire_at REAL
            )
        """)
        self._conn.commit()

    def get(self, key: str) -> Any:
        row = self._conn.execute(
            "SELECT data_type, data, expire_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None

        data_type, raw, expire_at = row
        if expire_at is not None and time.time() > expire_at:
            self.delete(key)
            return None

        if data_type == "json":
            return json.loads(raw)
        elif data_type == "dataframe":
            from io import BytesIO

            buf = BytesIO(raw)
            return pd.read_parquet(buf)
        return None

    def set(
        self,
        key: str,
        data: Any,
        ttl_seconds: float | None = None,
        expire_at: float | None = None,
    ) -> None:
        if ttl_seconds is not None:
            expire_at = time.time() + ttl_seconds

        if isinstance(data, pd.DataFrame):
            from io import BytesIO

            buf = BytesIO()
            data.to_parquet(buf, index=False)
            raw = buf.getvalue()
            data_type = "dataframe"
        else:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            data_type = "json"

        self._conn.execute(
            """
            INSERT OR REPLACE INTO cache (key, data_type, data, expire_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, data_type, raw, expire_at),
        )
        self._conn.commit()

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()

    def keys(self) -> list[str]:
        rows = self._conn.execute("SELECT key FROM cache").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        self._conn.close()
