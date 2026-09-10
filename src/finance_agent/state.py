from operator import add
from typing import Annotated, Literal, TypedDict

import pandas as pd


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Send 并行 agent 的 dict 合并 reducer。"""
    result = dict(left or {})
    result.update(right or {})
    return result


class AnalysisState(TypedDict, total=False):
    # ── 输入 ──
    query: str
    stock_code: str
    stock_name: str
    analysis_type: Literal["financial", "investment", "comprehensive"]
    peer_codes: list[str] | None
    enable_web_search: bool  # 是否启用实时事件搜索
    api_key: str | None  # 用户自带的 DeepSeek API Key（HF Spaces 用）
    focus: str  # 深度研究意图澄清环节用户填写的关注点（Kimi 风格反问回答）

    # ── Cache ──
    cache_result: str  # HIT | MISS

    # ── Validation ──
    validation_result: str  # PASS | FAIL
    validation_warnings: list[str]

    # ── Layer 1: 基础公共数据 ──
    balance_sheet: pd.DataFrame
    income_statement: pd.DataFrame
    cash_flow_statement: pd.DataFrame
    stock_quote: dict
    industry_info: dict

    # ── Layer 2: 分析导向 (MVP: 仅预计算指标) ──
    financial_indicators: pd.DataFrame | None
    industry_pe: dict | None

    # ── Layer 3: 衍生计算 ──
    solvency_metrics: dict
    profitability_metrics: dict
    efficiency_metrics: dict
    cashflow_metrics: dict
    dupont_tree: dict
    growth_rates: dict
    anomalies: list
    traffic_lights: dict
    health_score: dict | None

    # ── Layer 3 扩展: 同业+估值 ──
    peer_financials: pd.DataFrame | None
    peer_comparison: dict | None
    relative_valuation: dict | None
    garp_result: dict | None

    # ── Layer 3 扩展: 季度趋势 ──
    quarterly_income: pd.DataFrame | None
    quarterly_trend: dict | None

    # ── Layer 2.5: 关键非财务事件（舆情分析师输入之一）──
    key_events: list[dict] | None

    # ── Agent 输出 ──
    final_report: str | None
    file_path: str | None
    file_paths: dict | None

    # ── 5 层架构（ADR-0011）──

    # PREP 扩展
    kline: pd.DataFrame  # 日 K 线（OHLCV）
    benchmark_kline: pd.DataFrame  # 沪深 300 K 线
    technical_indicators: dict  # calc_technical() 输出
    risk_metrics: dict  # calc_risk() 输出
    macro_indicators: dict  # CPI/PMI/M2/LPR
    news_list: list[dict]  # 新闻列表

    # Layer I: Analyst Team（4 个并行分析师）
    analyst_reports: Annotated[dict[str, dict], merge_dicts]

    # Layer II: Researcher Team（Bull/Bear 辩论）
    debate_history: Annotated[list[dict], add]
    focus_summary: str  # 研究聚焦摘要（report 节点无条件生成，judge report_conclusion 直取源）
    research_manager_conclusion: str  # 评级前置拼装（RM 结构化输出的人读渲染）
    research_manager_rating: str | None  # 看多/看空/中性（战绩结算与 judge 变量直取）
    research_manager_confidence: float | None

    # Layer III: Trader
    trader_plan: dict  # TradeDecision 序列化

    # Layer IV: Risk Management（3 辩论者 + Risk Judge）
    risk_debate_history: Annotated[list[dict], add]
    final_trade_decision: dict  # TradeDecision 序列化

    # Layer V: Fund Manager
    fund_manager_decision: Literal["approve", "reject", "return"]
    fund_manager_decision_reasoning: str  # FM 退回/批准理由（回路契约：未声明则被图合并丢弃）
    fund_manager_action: str | None  # FM 操作定性（approve 必有；reject/return 为 None）
    fund_manager_confidence: float | None  # FM 对操作定性的把握（approve 必有）
    return_count: int  # 退回次数（上限 1）
    langfuse_trace_id: str  # fund_manager approve 时捕获,decision_log 反向上报用

    # 引用校验（ADR-0010 Step 3）
    citation_report: dict  # CitationReport 序列化
    citation_pass: bool
    iteration_count: int  # 重试次数（上限 3）
    # 各轮校验失败率历史（citation-retry-policy delta）：失败率停滞时
    # after_citation 提前放行渲染，不再全量重跑分析师
    citation_fail_rates: list[float]
    citation_minor_fail: bool  # 轻微失败降级放行（skip-citation-retry-on-minor-failures）
    # harden-citation-semantic-coverage：FAIL 分桶与定向重试
    citation_retry_targets: list[str]  # 值级 FAIL 分析师（Send 定向重跑）
    citation_retry_feedback: dict[str, list[dict]]  # 每分析师失败明细（重试上下文注入）
    citation_fail_buckets: dict[str, int]  # 桶计数（value_mismatch/path_unresolvable/...）
    citation_coverage: float  # 正文数字普查覆盖率（0-1，监控不进路由）

    # ── URL 信源溯源（Kimi 风格引用）──
    web_sources: list[dict]  # [{"query","title","url","content"}]

    # ── 图表数据（用于前端 ECharts + docx/pptx PNG）──
    chart_data: dict  # 结构化财务/股价序列，JSON-serializable
