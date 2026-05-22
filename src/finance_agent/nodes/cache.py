"""check_cache: 查缓存，返回 HIT / MISS。

HIT = 三大报表全部缓存命中且未过期。
MISS = 任一报表缺失或过期。
"""

from __future__ import annotations

from finance_agent.data.cache import DataCache

_CACHE: DataCache | None = None


def _get_cache(cache=None) -> DataCache:
    if cache is not None:
        return cache
    global _CACHE
    if _CACHE is None:
        _CACHE = DataCache()
    return _CACHE


def check_cache(state: dict, cache=None) -> dict:
    code = state.get("stock_code", "")
    c = _get_cache(cache)

    keys = [
        f"{code}:balance_sheet",
        f"{code}:income_statement",
        f"{code}:cash_flow_statement",
    ]

    cached = {}
    for key in keys:
        val = c.get(key)
        if val is None:
            return {"cache_result": "MISS"}
        cached[key] = val

    return {
        "cache_result": "HIT",
        "balance_sheet": cached[f"{code}:balance_sheet"],
        "income_statement": cached[f"{code}:income_statement"],
        "cash_flow_statement": cached[f"{code}:cash_flow_statement"],
    }
