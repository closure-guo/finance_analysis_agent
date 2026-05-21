from typing import TypedDict, Optional, Literal
import pandas as pd


class AnalysisState(TypedDict, total=False):
    # ── 输入 ──
    query: str
    stock_code: str
    analysis_type: Literal["financial", "investment", "comprehensive"]
    peer_codes: Optional[list[str]]

    # ── Cache ──
    cache_result: str  # FULL_HIT | RAW_HIT | MISS

    # ── Layer 1: 基础公共数据 ──
    balance_sheet: pd.DataFrame
    income_statement: pd.DataFrame
    cash_flow_statement: pd.DataFrame
    stock_quote: dict
    industry_info: dict

    # ── Layer 2: 分析导向 (MVP: 仅预计算指标) ──
    financial_indicators: Optional[pd.DataFrame]

    # ── Layer 3: 衍生计算 ──
    solvency_metrics: dict
    profitability_metrics: dict
    efficiency_metrics: dict
    cashflow_metrics: dict
    dupont_tree: dict
    growth_rates: dict
    anomalies: list
    traffic_lights: dict

    # ── Layer 3 扩展: 同业+估值 ──
    peer_financials: Optional[pd.DataFrame]
    peer_comparison: Optional[dict]
    relative_valuation: Optional[dict]
    garp_result: Optional[dict]

    # ── Agent 输出 ──
    financial_analysis: Optional[str]
    financial_report: Optional[str]
    investment_analysis: Optional[str]
    investment_report: Optional[str]
    final_report: Optional[str]
    file_path: Optional[str]
