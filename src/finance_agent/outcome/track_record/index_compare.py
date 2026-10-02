"""指数区间收益对比(add-index-performance-compare)。

指数收盘落库与区间收益读数;win/loss 判定基准仍为 BENCHMARK_CODE(沪深300),
判定链路不消费本模块。口径细则见 openspec/changes/add-index-performance-compare
的 specs/index-comparison。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from finance_agent.outcome.track_record.model import upsert_index_closes

logger = logging.getLogger(__name__)

# 对比指数集(代码级常量,非配置项——见 design Non-Goals)
INDEX_COMPARE_UNIVERSE: list[dict[str, str]] = [
    {"code": "000001", "name": "上证指数"},
    {"code": "000300", "name": "沪深300"},
    {"code": "000905", "name": "中证500"},
    {"code": "000852", "name": "中证1000"},
    {"code": "399006", "name": "创业板指"},
]


def sync_index_closes(
    *,
    client: Any = None,
    db_path: str | Path | None = None,
    days: int = 280,
) -> dict[str, Any]:
    """拉取指数集 K 线并幂等落库;单指数失败仅 WARNING,不外抛。

    日批(daily_marking)与回填脚本共用:days 为拉取的交易日长度,
    280 交易日 ≈ 1.1 年,覆盖前端最长 1y 窗口。返回 {stored, failed}。
    """
    if client is None:
        from finance_agent.data.akshare_client import AKShareClient

        client = AKShareClient()
    stored = 0
    failed: list[str] = []
    for u in INDEX_COMPARE_UNIVERSE:
        code = u["code"]
        try:
            df = client.fetch_index_kline(code, days=days)
            if df is None or df.empty:
                # 空行情仅告警跳过,不进 failed(failed 只收异常码,单指数缺数不放大)
                logger.warning("指数 %s(%s) 行情为空,本批跳过", code, u["name"])
                continue
            rows = [(code, str(d), float(c)) for d, c in zip(df["日期"], df["收盘"], strict=False)]
            stored += upsert_index_closes(rows, db_path=db_path)
        except Exception as e:  # noqa: BLE001 - 单指数失败隔离,展示层不得放大
            failed.append(code)
            logger.warning("指数 %s(%s) 收盘落库失败: %s", code, u["name"], e)
    return {"stored": stored, "failed": failed}
