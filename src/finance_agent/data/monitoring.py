"""数据源拉取监控：进程内命中/未命中/失败计数（非持久化，进程重启清零）。"""

import threading
import time


class DataSourceMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._fails: dict[str, int] = {}
        self._last_hit: float | None = None

    def record_hit(self) -> None:
        with self._lock:
            self._hits += 1
            self._last_hit = time.time()

    def record_miss(self) -> None:
        with self._lock:
            self._misses += 1

    def record_fail(self, label: str) -> None:
        with self._lock:
            self._fails[label] = self._fails.get(label, 0) + 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "fails": dict(self._fails),
                "last_hit": self._last_hit,
            }


_monitor: DataSourceMonitor | None = None


def get_monitor() -> DataSourceMonitor:
    global _monitor
    if _monitor is None:
        _monitor = DataSourceMonitor()
    return _monitor


def reset_monitor_for_tests() -> None:
    global _monitor
    _monitor = None
