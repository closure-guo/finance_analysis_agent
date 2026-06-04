"""事件模块配置。"""

from __future__ import annotations

import os

# 权威财经新闻域名白名单
ALLOWED_DOMAINS: tuple[str, ...] = (
    # 主流财经媒体
    "caixin.com",
    "stcn.com",
    "cs.com.cn",
    "eastmoney.com",
    "hexun.com",
    "sina.com.cn",
    "sohu.com",
    "163.com",
    "ifeng.com",
    # 证券/研报平台
    "10jqka.com",
    "stockstar.com",
    "cnfol.com",
    "baogaoting.com",
    "pedaily.cn",
    "cnyes.com",
)

# 事件数据源配置
# builtin: 只读预构建库（零外部依赖）
# auto: WebSearch 优先 → 预构建库降级 → 兜底
EVENT_SOURCE: str = os.environ.get("EVENT_SOURCE", "auto")

DEMO_MODE: bool = EVENT_SOURCE == "builtin"

# WebSearch 查询模板
WEBSEARCH_QUERY_TEMPLATE: str = "{stock_name} {stock_code} {year_range} 提价 渠道 业绩 产品"

# 时间窗口（天）
EVENT_CUTOFF_DAYS: int = 1095  # 3 年，确保 demo 数据（2024 年事件）完整展示
