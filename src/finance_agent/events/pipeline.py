"""事件获取流水线：L2 WebSearch → L1 预构建库 → L3 兜底。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from finance_agent.events.config import EVENT_CUTOFF_DAYS
from finance_agent.events.fallback import fallback_annotation
from finance_agent.events.preset_loader import load_preset_events

logger = logging.getLogger(__name__)


def fetch_key_events(
    stock_code: str, stock_name: str = "", use_web_search: bool = True
) -> list[dict]:
    """获取关键非财务事件。

    默认流程（use_web_search=True）：
    1. L2: WebSearch 实时搜索
    2. L1: 预构建库 key_events.json（WebSearch 失败时降级）
    3. L3: 兜底提示（两者都失败时）

    关闭 WebSearch（use_web_search=False）：
    1. L1: 预构建库
    2. L3: 兜底

    返回事件列表（永远不会空，L3 兜底保证）。
    """
    # ── L2: WebSearch（默认优先）──
    if use_web_search:
        try:
            from finance_agent.events.web_fetcher import fetch_events_from_web

            web_events = fetch_events_from_web(stock_code, stock_name)
            if web_events:
                logger.info("WebSearch returned %d events for %s", len(web_events), stock_code)
                return _filter_events(web_events)
        except Exception as e:
            logger.warning("WebSearch failed for %s: %s", stock_code, e)

    # ── L1: 预构建库（WebSearch 降级或关闭时）──
    preset = load_preset_events(stock_code)
    if preset is not None:
        # 结构性空（[]）或有数据（list）
        if preset:
            logger.info("Preset events returned %d events for %s", len(preset), stock_code)
        return _filter_events(preset)

    # L1 未命中（股票不在库中）
    # ── L3: 兜底 ──
    return fallback_annotation()


def _filter_events(events: list[dict]) -> list[dict]:
    """过滤事件：只保留最近 N 天，ongoing=True 除外。"""
    if not events:
        return []

    cutoff = datetime.now() - timedelta(days=EVENT_CUTOFF_DAYS)
    result: list[dict] = []

    for e in events:
        # ongoing 事件始终保留
        if e.get("ongoing"):
            result.append(e)
            continue

        # 检查日期
        date_str = e.get("date", "")
        if not date_str:
            continue
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            if event_date >= cutoff:
                result.append(e)
        except ValueError:
            # 日期格式异常，保留（避免误删）
            result.append(e)

    return result
