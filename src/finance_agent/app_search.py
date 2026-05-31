"""Stock search with fuzzy matching for Gradio dropdown."""

from __future__ import annotations

import akshare as ak

_STOCK_LIST_CACHE: list[dict] | None = None


def get_stock_list() -> list[dict]:
    """Fetch A-share stock list from AKShare (cached in memory)."""
    global _STOCK_LIST_CACHE
    if _STOCK_LIST_CACHE is None:
        try:
            df = ak.stock_zh_a_spot_em()
            _STOCK_LIST_CACHE = [
                {"code": str(row["代码"]), "name": str(row["名称"])}
                for _, row in df.iterrows()
            ]
        except Exception:
            _STOCK_LIST_CACHE = []
    return _STOCK_LIST_CACHE


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
