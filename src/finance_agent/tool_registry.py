"""Agent 工具权威注册表（harden-eval-implementation-decoupling）。

工具名唯一权威来源：agent_factory 注册名与 evals/toolcall 默认允许集均引用
此处的常量，避免「评估与实现各维护一份允许集」导致漂移（构造性一致防御：
同源点应是一个注册表，而不是各自副本）。
"""

from __future__ import annotations

TOOL_WEB_SEARCH = "web_search"
TOOL_BATCH_WEB_SEARCH = "batch_web_search"
TOOL_SEARCH_STOCK = "search_stock"
TOOL_RUN_DEEP_ANALYSIS = "run_deep_analysis"

# 全部已注册工具（quick/deep/follow-up 模式）
AGENT_TOOL_NAMES = frozenset(
    {
        TOOL_WEB_SEARCH,
        TOOL_BATCH_WEB_SEARCH,
        TOOL_SEARCH_STOCK,
        TOOL_RUN_DEEP_ANALYSIS,
    }
)
