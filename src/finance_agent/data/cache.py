"""SQLite 缓存读写 + TTL 过期。

接口：
- get(key) → data | None
- set(key, data, ttl_seconds=None, expire_at=None)
- delete(key)
- keys() → list[str]
- get_shared_cache() → 进程级共享单例（nodes 层统一入口）

data 支持 dict 和 pd.DataFrame，内部序列化为 JSON/Parquet 存入 SQLite。

线程安全（2026-09-08 缓存层审计修复）：共享 Connection 无锁时并发
execute 报 InterfaceError 且写入静默丢失（实测 400 并发写只成功 200）。
所有 Connection 操作（get/set/delete/keys/close）经 threading.Lock 串行化；
缓存操作为微秒-毫秒级，锁竞争可忽略。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

import pandas as pd


class DataCache:
    def __init__(self, db_path: str = "cache.db"):
        self._db_path = db_path
        # RLock（可重入）：get 内部过期删除调用 delete，Lock 会死锁
        self._lock = threading.RLock()
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
        with self._lock:
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

        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, data_type, data, expire_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, data_type, raw, expire_at),
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()

    def keys(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT key FROM cache").fetchall()
            return [r[0] for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ── 进程级共享单例（2026-09-08 统一：此前 nodes/cache 与 nodes/fetch 各自
# DataCache() 单例——两个 Connection 指向同一 cache.db，加倍并发冲突面且
# 语义分裂。统一入口后跨模块读写经同一有锁实例。）──
_SHARED: DataCache | None = None


def get_shared_cache() -> DataCache:
    global _SHARED
    if _SHARED is None:
        _SHARED = DataCache()
    return _SHARED
