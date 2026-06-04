"""check_cache: 查缓存，返回 HIT / MISS。

HIT = 三大报表 + 行业归属 + 行情数据全部缓存命中且未过期。
MISS = 任一 key 缺失或过期。

TTL 策略（ADR-0004）：
- 三大报表：永久（历史事实不可变）
- 行业归属：30 天
- 行情数据 / 行业 PE：1 天
- 预计算指标：同三大报表（永久）
"""

from __future__ import annotations

from finance_agent.data.cache import DataCache

_CACHE: DataCache | None = None


def _get_cache(cache: DataCache | None = None) -> DataCache:
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
        f"{code}:industry_info",
        f"{code}:stock_quote",
    ]

    cached = {}
    for key in keys:
        val = c.get(key)
        if val is None:
            return {"cache_result": "MISS"}
        cached[key] = val

    result = {
        "cache_result": "HIT",
        "balance_sheet": cached[f"{code}:balance_sheet"],
        "income_statement": cached[f"{code}:income_statement"],
        "cash_flow_statement": cached[f"{code}:cash_flow_statement"],
        "industry_info": cached.get(f"{code}:industry_info", {}),
        "stock_quote": cached.get(f"{code}:stock_quote", {}),
    }

    # 预计算指标和 industry_pe 有则附带（无则 MISS 时重拉）
    indicators = c.get(f"{code}:indicators")
    if indicators is not None:
        result["financial_indicators"] = indicators
    industry_pe = c.get(f"{code}:industry_pe")
    if industry_pe is not None:
        result["industry_pe"] = industry_pe

    # key_events 有则附带
    key_events = c.get(f"{code}:key_events")
    if key_events is not None:
        result["key_events"] = key_events

    return result
