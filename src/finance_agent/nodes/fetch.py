"""fetch_data: 从 AKShare 拉取三大报表 + 行情 + 行业归属 + 同业数据。

Step1 并行：三大报表 + 行情 + 行业归属 + 预计算指标（无依赖）
Step2 依赖：同业公司数据（需要行业归属结果）

数据降级：
- 三大报表缺失 → 抛异常终止
- 同业/行情缺失 → 标记 N/A 继续

TESTING=1：返回确定性 stub 数据（不触网），供管线 E2E 确定性运行
（agent-turn-box-display delta task 5.5）。stub 三大报表满足勾稽校验
硬等式（资产=负债+权益），行数/年份对齐（最新在前），使
validate_financials PASS、compute_metrics 可用。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.data.cache import DataCache

logger = logging.getLogger(__name__)

_CACHE: DataCache | None = None
_CLIENT: AKShareClient | None = None


def _make_stub_balance_sheet() -> pd.DataFrame:
    """确定性资产负债表（2 年，最新在前；资产 = 负债 + 权益 严格成立）。"""
    return pd.DataFrame(
        {
            "报告日": ["20241231", "20231231"],
            "资产总计": [1000.0, 900.0],
            "负债合计": [400.0, 360.0],
            "所有者权益(或股东权益)合计": [600.0, 540.0],
            "归母所有者权益": [600.0, 540.0],
            "流动资产合计": [500.0, 450.0],
            "流动负债合计": [200.0, 180.0],
            "存货": [50.0, 45.0],
            "货币资金": [100.0, 90.0],
            "短期借款": [10.0, 9.0],
            "长期借款": [20.0, 18.0],
            "应付债券": [0.0, 0.0],
            "一年内到期的非流动负债": [0.0, 0.0],
            "累计折旧": [30.0, 25.0],
            "未分配利润": [300.0, 270.0],
        }
    )


def _make_stub_income_statement() -> pd.DataFrame:
    """确定性利润表（净利润 = 利润总额 - 所得税 严格成立）。"""
    return pd.DataFrame(
        {
            "报告日": ["20241231", "20231231"],
            "营业收入": [1000.0, 900.0],
            "营业成本": [600.0, 540.0],
            "利润总额": [100.0, 90.0],
            "所得税费用": [25.0, 22.5],
            "净利润": [75.0, 67.5],
            "归母净利润": [75.0, 67.5],
            "利息费用": [5.0, 4.5],
        }
    )


def _make_stub_cash_flow() -> pd.DataFrame:
    """确定性现金流量表（经营+投资+筹资 = 现金净变动 严格成立）。"""
    return pd.DataFrame(
        {
            "报告日": ["20241231", "20231231"],
            "经营活动产生的现金流量净额": [80.0, 72.0],
            "投资活动产生的现金流量净额": [-30.0, -27.0],
            "筹资活动产生的现金流量净额": [-20.0, -18.0],
            "现金及现金等价物净增加额": [30.0, 27.0],
            "分配股利、利润或偿付利息所支付的现金": [20.0, 18.0],
        }
    )


def _stub_fetch_data(state: dict) -> dict[str, Any]:
    """TESTING=1 专用的确定性数据：不触网，字段与真实 fetch_data 输出一致。"""
    stock_name = state.get("stock_name", "") or state.get("stock_code", "")
    return {
        "balance_sheet": _make_stub_balance_sheet(),
        "income_statement": _make_stub_income_statement(),
        "cash_flow_statement": _make_stub_cash_flow(),
        "financial_indicators": None,
        "industry_info": {"industry": "白酒", "name": stock_name},
        "stock_quote": {"price": 1800.0, "name": stock_name, "code": state.get("stock_code", "")},
        "key_events": [],
        "peer_financials": None,
        "macro_indicators": {},
        "news_list": [],
    }


def _get_cache(cache: DataCache | None = None) -> DataCache:
    if cache is not None:
        return cache
    global _CACHE
    if _CACHE is None:
        _CACHE = DataCache()
    return _CACHE


def _get_client(client: AKShareClient | None = None) -> AKShareClient:
    if client is not None:
        return client
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = AKShareClient()
    return _CLIENT


def fetch_data(state: dict, cache=None, client=None) -> dict:
    # TESTING=1：确定性 stub（不触 AKShare/网络），供管线 E2E 使用
    if os.getenv("TESTING") == "1":
        return _stub_fetch_data(state)

    code = state.get("stock_code", "")
    c = _get_cache(cache)
    ak = _get_client(client)

    result: dict[str, Any] = {}

    # Step 1: 必需数据（缺失报错）
    bs = ak.fetch_balance_sheet(code)
    c.set(f"{code}:balance_sheet", bs)
    result["balance_sheet"] = bs

    is_df = ak.fetch_income_statement(code)
    c.set(f"{code}:income_statement", is_df)
    result["income_statement"] = is_df

    cf = ak.fetch_cash_flow(code)
    c.set(f"{code}:cash_flow_statement", cf)
    result["cash_flow_statement"] = cf

    # Step 1: 非必需数据（缺失标记 N/A）
    try:
        indicators = ak.fetch_indicators(code)
        c.set(f"{code}:indicators", indicators)
        result["financial_indicators"] = indicators
    except Exception as e:
        logger.warning("预计算指标拉取失败: %s", e)
        result["financial_indicators"] = None

    try:
        industry = ak.fetch_industry(code)
        c.set(f"{code}:industry_info", industry, ttl_seconds=2_592_000)
        result["industry_info"] = industry
    except Exception as e:
        logger.warning("行业归属拉取失败: %s", e)
        result["industry_info"] = {}

    try:
        quote = ak.fetch_stock_quote(code)
        c.set(f"{code}:stock_quote", quote, ttl_seconds=86_400)
        result["stock_quote"] = quote
    except Exception as e:
        logger.warning("行情数据拉取失败: %s", e)
        result["stock_quote"] = {}

    # K 线数据（技术指标 + 风控指标依赖）
    try:
        kline = ak.fetch_kline(code)
        if not kline.empty:
            c.set(f"{code}:kline", kline, ttl_seconds=3600)
            result["kline"] = kline
        else:
            logger.warning("K线数据为空: %s", code)
    except Exception as e:
        logger.warning("K线数据拉取失败: %s", e)

    try:
        benchmark = ak.fetch_benchmark_kline()
        if not benchmark.empty:
            c.set("benchmark_kline", benchmark, ttl_seconds=3600)
            result["benchmark_kline"] = benchmark
    except Exception as e:
        logger.warning("沪深300 K线拉取失败: %s", e)

    try:
        industry_pe = ak.fetch_industry_pe(code)
        if industry_pe:
            c.set(f"{code}:industry_pe", industry_pe, ttl_seconds=86_400)
            result["industry_pe"] = industry_pe
    except Exception as e:
        logger.warning("行业PE拉取失败: %s", e)

    # Step 1: 季度数据（非必需，失败不阻塞）
    try:
        q_income = ak.fetch_quarterly_income(code)
        c.set(f"{code}:quarterly_income", q_income)
        result["quarterly_income"] = q_income
    except Exception as e:
        logger.warning("季度利润表拉取失败: %s", e)
        result["quarterly_income"] = None

    # Step 1: 关键非财务事件（非必需，失败不阻塞，降级安全）
    try:
        from finance_agent.events.pipeline import fetch_key_events

        use_web = state.get("enable_web_search", True)
        events = fetch_key_events(
            code,
            (result.get("industry_info") or {}).get("name", ""),
            use_web_search=use_web,
        )
        c.set(f"{code}:key_events", events)
        result["key_events"] = events
    except Exception as e:
        logger.warning("关键事件获取失败: %s", e)
        result["key_events"] = []

    # Step 2: 同业数据（依赖行业归属）
    try:
        peers = _fetch_peers(ak, code, state, result.get("industry_info"))
        if peers is not None:
            result["peer_financials"] = peers
    except Exception as e:
        logger.warning("同业数据拉取失败: %s", e)
        result["peer_financials"] = None

    # Step 2: 宏观指标（非必需，失败不阻塞）
    try:
        macro = ak.fetch_macro_indicators()
        c.set("macro_indicators", macro, ttl_seconds=86_400)
        result["macro_indicators"] = macro
    except Exception as e:
        logger.warning("宏观指标拉取失败: %s", e)
        result["macro_indicators"] = {}

    # Step 2: 新闻资讯（非必需，失败不阻塞）
    try:
        news = ak.fetch_news(code)
        c.set(f"{code}:news", news, ttl_seconds=3600)
        result["news_list"] = news
    except Exception as e:
        logger.warning("新闻资讯拉取失败: %s", e)
        result["news_list"] = []

    return result


def _fetch_peers(ak, code, state, industry_info):
    peer_codes = state.get("peer_codes")
    if not peer_codes or not industry_info:
        return None
    return ak.fetch_peer_data(peer_codes)
