"""fetch_data: 从 AKShare 拉取三大报表 + 行情 + 行业归属 + 同业数据。

Step1 并行：三大报表 + 行情 + 行业归属 + 预计算指标（无依赖）
Step2 依赖：同业公司数据（需要行业归属结果）

数据降级：
- 三大报表缺失 → 抛异常终止
- 同业/行情缺失 → 标记 N/A 继续
"""

from __future__ import annotations

import logging

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.data.cache import DataCache

logger = logging.getLogger(__name__)

_CACHE: DataCache | None = None
_CLIENT: AKShareClient | None = None


def _get_cache(cache=None) -> DataCache:
    if cache is not None:
        return cache
    global _CACHE
    if _CACHE is None:
        _CACHE = DataCache()
    return _CACHE


def _get_client(client=None) -> AKShareClient:
    if client is not None:
        return client
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = AKShareClient()
    return _CLIENT


def fetch_data(state: dict, cache=None, client=None) -> dict:
    code = state.get("stock_code", "")
    c = _get_cache(cache)
    ak = _get_client(client)

    result = {}

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
        result["financial_indicators"] = indicators
    except Exception as e:
        logger.warning("预计算指标拉取失败: %s", e)
        result["financial_indicators"] = None

    try:
        industry = ak.fetch_industry(code)
        result["industry_info"] = industry
    except Exception as e:
        logger.warning("行业归属拉取失败: %s", e)
        result["industry_info"] = {}

    try:
        quote = ak.fetch_stock_quote(code)
        result["stock_quote"] = quote
    except Exception as e:
        logger.warning("行情数据拉取失败: %s", e)
        result["stock_quote"] = {}

    try:
        industry_pe = ak.fetch_industry_pe(code)
        if industry_pe:
            result["industry_pe"] = industry_pe
    except Exception as e:
        logger.warning("行业PE拉取失败: %s", e)

    # Step 2: 同业数据（依赖行业归属）
    try:
        peers = _fetch_peers(ak, code, state, result.get("industry_info"))
        if peers is not None:
            result["peer_financials"] = peers
    except Exception as e:
        logger.warning("同业数据拉取失败: %s", e)
        result["peer_financials"] = None

    return result


def _fetch_peers(ak, code, state, industry_info):
    peer_codes = state.get("peer_codes")
    if not peer_codes or not industry_info:
        return None
    return ak.fetch_peer_data(peer_codes)
