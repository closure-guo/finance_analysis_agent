"""L1: 预构建事件库加载器。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 数据文件路径（相对于项目根目录）
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_KEY_EVENTS_FILE = _DATA_DIR / "key_events.json"

# 内存缓存
_cache: dict[str, Any] | None = None


def _load_json() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    if not _KEY_EVENTS_FILE.exists():
        logger.warning("key_events.json not found at %s", _KEY_EVENTS_FILE)
        _cache = {}
        return _cache
    try:
        with open(_KEY_EVENTS_FILE, encoding="utf-8") as f:
            _cache = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load key_events.json: %s", e)
        _cache = {}
    return _cache


def load_preset_events(stock_code: str) -> list[dict] | None:
    """从预构建库加载事件。

    Returns:
        - 股票在库中有事件 → list[dict]
        - 股票在库中但事件为空列表 → []（结构性空）
        - 股票不在库中 → None（触发 L2/L3）
    """
    data = _load_json()
    events_map = data.get("events", {})
    if stock_code not in events_map:
        return None
    events = events_map[stock_code]
    if not isinstance(events, list):
        logger.warning("Invalid events type for %s: %s", stock_code, type(events))
        return None
    return events
