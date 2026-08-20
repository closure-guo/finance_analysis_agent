# src/finance_agent/llm/probe_cache.py — probe 结果缓存（设计档案 §13）。
"""ProbeReport 结果缓存（设计档案 §13）。

缓存键为五要素哈希：provider / model / base_url / api_key 的 sha256 /
litellm version——任一变化（尤其 litellm 升级导致行为漂移）即视为不同键，
旧缓存自然失效。条目带 TTL（默认 86400s），过期即清除；线程安全
（`threading.Lock`），供多 Agent 并发复用 probe 结果、避免重复真实调用。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import threading
import time

from finance_agent.llm.probes import ProbeReport


def _litellm_version() -> str:
    try:
        return importlib.metadata.version("litellm")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def cache_key(*, model: str, base_url: str | None, api_key: str | None) -> str:
    """五要素缓存键：provider|model|base_url|sha256(api_key)|litellm_version。"""
    provider = model.split("/", 1)[0] if "/" in model else ""
    raw = "|".join(
        [
            provider,
            model,
            base_url or "",
            hashlib.sha256((api_key or "").encode()).hexdigest(),
            _litellm_version(),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class ProbeCache:
    """线程安全的 ProbeReport TTL 缓存。"""

    def __init__(self, default_ttl_seconds: float = 86400.0) -> None:
        self._default_ttl_seconds = default_ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[ProbeReport, float]] = {}

    def get(self, key: str) -> ProbeReport | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            report, expiry = entry
            if time.monotonic() >= expiry:
                del self._store[key]
                return None
            return report

    def put(self, key: str, report: ProbeReport, ttl_seconds: float | None = None) -> None:
        ttl = self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._store[key] = (report, time.monotonic() + ttl)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_probe_cache: ProbeCache | None = None


def get_probe_cache() -> ProbeCache:
    """模块级单例。"""
    global _probe_cache
    if _probe_cache is None:
        _probe_cache = ProbeCache()
    return _probe_cache


def _reset_probe_cache_for_tests() -> None:
    """测试隔离：重置单例。"""
    global _probe_cache
    _probe_cache = None
