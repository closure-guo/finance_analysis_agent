"""Stock search with fuzzy matching for Gradio dropdown."""

from __future__ import annotations

import logging
import time

import akshare as ak

logger = logging.getLogger(__name__)

_STOCK_LIST_CACHE: list[dict] | None = None
_STOCK_LIST_FAILURE_TS: float = 0.0
# 失败后的重试冷却：冷却期内直接返回空列表，不反复打上游（单次全量抓取约 5-30s）
_FAILURE_RETRY_COOLDOWN_SECONDS = 60.0
# 完整 A 股列表 >5000 只；低于此阈值视为抓取不完整，拒绝缓存（防止半截列表毒化锚点）
_MIN_VALID_LIST_SIZE = 1000


def get_stock_list() -> list[dict]:
    """Fetch A-share stock list from AKShare (cached in memory).

    失败语义：抓取异常或结果可疑（低于 _MIN_VALID_LIST_SIZE）时返回空列表，
    但**不缓存**——冷却期过后下次调用自动重试。空列表只代表「本次不可用」，
    不代表「数据库无此股票」；调用方不得把失败结果当成功缓存。
    """
    global _STOCK_LIST_CACHE, _STOCK_LIST_FAILURE_TS
    if _STOCK_LIST_CACHE is not None:
        return _STOCK_LIST_CACHE

    if time.monotonic() - _STOCK_LIST_FAILURE_TS < _FAILURE_RETRY_COOLDOWN_SECONDS:
        return []

    try:
        df = ak.stock_info_a_code_name()
        stocks = [{"code": str(row["code"]), "name": str(row["name"])} for _, row in df.iterrows()]
        if len(stocks) < _MIN_VALID_LIST_SIZE:
            raise ValueError(
                f"股票列表异常小（{len(stocks)} 只，阈值 {_MIN_VALID_LIST_SIZE}），疑似抓取不完整"
            )
        _STOCK_LIST_CACHE = stocks
        return _STOCK_LIST_CACHE
    except Exception:
        logger.warning(
            "AKShare stock_info_a_code_name 抓取失败，本次返回空列表（不缓存，%.0fs 冷却后自动重试）",
            _FAILURE_RETRY_COOLDOWN_SECONDS,
            exc_info=True,
        )
        _STOCK_LIST_FAILURE_TS = time.monotonic()
        return []


def search_stocks(query: str, limit: int = 20) -> list[tuple[str, str]]:
    """Return (display_label, code) tuples matching query.

    Matches on stock name or code (case-insensitive).
    """
    if not query:
        return []

    stocks = get_stock_list()
    query_lower = query.lower()
    matches: list[tuple[str, str]] = []

    for s in stocks:
        code = s["code"]
        name = s["name"]
        if query_lower in code.lower() or query_lower in name.lower():
            label = f"{name} ({code})"
            matches.append((label, code))
            if len(matches) >= limit:
                break

    return matches
