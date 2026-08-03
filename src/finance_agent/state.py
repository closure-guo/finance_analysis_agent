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
    research_manager_conclusion: str

    # Layer III: Trader
    trader_plan: dict  # TradeDecision 序列化

    # Layer IV: Risk Management（3 辩论者 + Risk Judge）
    risk_debate_history: Annotated[list[dict], add]
    final_trade_decision: dict  # TradeDecision 序列化

    # Layer V: Fund Manager
    fund_manager_decision: Literal["approve", "reject", "return"]
    return_count: int  # 退回次数（上限 1）

    # 引用校验（ADR-0010 Step 3）
    citation_report: dict  # CitationReport 序列化
    citation_pass: bool
    iteration_count: int  # 重试次数（上限 3）

    # ── URL 信源溯源（Kimi 风格引用）──
    web_sources: list[dict]  # [{"query","title","url","content"}]

    # ── 图表数据（用于前端 ECharts + docx/pptx PNG）──
    chart_data: dict  # 结构化财务/股价序列，JSON-serializable
