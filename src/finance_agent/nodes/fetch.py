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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.data.cache import DataCache
from finance_agent.langfuse_tracing import open_span

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


def _set_optional_fallback(result: dict, label: str) -> None:
    """非必需数据拉取失败时设置 fallback 值。"""
    fallbacks = {
        "financial_indicators": None,
        "industry_info": {},
        "stock_quote": {},
        "kline": None,
        "benchmark_kline": None,
        "industry_pe": None,
        "quarterly_income": None,
        "macro_indicators": {},
        "news_list": [],
    }
    result[label] = fallbacks.get(label)


def _summarize_success_output(value: Any) -> dict:
    """构造成功 span output：DataFrame → rows/columns 摘要。

    spec trace-observability「DataFrame 返回只记摘要」：AKShare 子调用返回
    pandas DataFrame 时，span output SHALL 只记 {"rows": N, "columns": [...]}
    摘要，不尝试序列化完整 DataFrame。列表/字典等非 DataFrame 类型只记 status
    （count / peer_count 等有用信息由调用方在 output 显式附加）。

    列表过长时（如三大报表几十列）截断到前 20 + "..."，避免 span 体积膨胀。
    """
    if isinstance(value, pd.DataFrame):
        columns = list(value.columns)
        if len(columns) > 20:
            columns = columns[:20] + ["..."]
        return {"status": "success", "rows": len(value), "columns": columns}
    return {"status": "success"}


def fetch_data(state: dict, cache=None, client=None) -> dict:
    # TESTING=1：确定性 stub（不触 AKShare/网络），供管线 E2E 使用
    if os.getenv("TESTING") == "1":
        return _stub_fetch_data(state)

    code = state.get("stock_code", "")
    c = _get_cache(cache)
    ak = _get_client(client)

    result: dict[str, Any] = {}

    # ── Step 1: 全部独立调用并行提交 ──
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures: dict = {}

        # 必需数据（缺失报错）
        futures[pool.submit(ak.fetch_balance_sheet, code)] = "balance_sheet"
        futures[pool.submit(ak.fetch_income_statement, code)] = "income_statement"
        futures[pool.submit(ak.fetch_cash_flow, code)] = "cash_flow_statement"

        # 非必需数据（缺失标记 N/A）
        futures[pool.submit(ak.fetch_indicators, code)] = "financial_indicators"
        futures[pool.submit(ak.fetch_industry, code)] = "industry_info"
        futures[pool.submit(ak.fetch_stock_quote, code)] = "stock_quote"
        futures[pool.submit(ak.fetch_kline, code)] = "kline"
        futures[pool.submit(ak.fetch_benchmark_kline)] = "benchmark_kline"
        futures[pool.submit(ak.fetch_industry_pe, code)] = "industry_pe"
        futures[pool.submit(ak.fetch_quarterly_income, code)] = "quarterly_income"
        futures[pool.submit(ak.fetch_macro_indicators)] = "macro_indicators"
        futures[pool.submit(ak.fetch_news, code)] = "news_list"

        # ── 收集结果（每个调用带 Langfuse span 追踪）──
        for future in as_completed(futures):
            label = futures[future]
            span_name = f"data_source:akshare:{label}"
            with open_span(span_name, input={"code": code, "label": label}) as obs:
                try:
                    value = future.result()
                    if obs:
                        obs.update(output=_summarize_success_output(value))
                except Exception as e:
                    if obs:
                        obs.update(output={"status": "error", "error": str(e)}, level="ERROR")
                    if label in ("balance_sheet", "income_statement", "cash_flow_statement"):
                        raise  # 必需数据异常传播，终止管线
                    logger.warning("%s 拉取失败: %s", label, e)
                    _set_optional_fallback(result, label)
                    continue

            # 按类型处理成功结果
            if label == "balance_sheet":
                c.set(f"{code}:balance_sheet", value)
                result["balance_sheet"] = value
            elif label == "income_statement":
                c.set(f"{code}:income_statement", value)
                result["income_statement"] = value
            elif label == "cash_flow_statement":
                c.set(f"{code}:cash_flow_statement", value)
                result["cash_flow_statement"] = value
            elif label == "financial_indicators":
                c.set(f"{code}:indicators", value)
                result["financial_indicators"] = value
            elif label == "industry_info":
                c.set(f"{code}:industry_info", value, ttl_seconds=2_592_000)
                result["industry_info"] = value
            elif label == "stock_quote":
                c.set(f"{code}:stock_quote", value, ttl_seconds=86_400)
                result["stock_quote"] = value
            elif label == "kline":
                if not value.empty:
                    c.set(f"{code}:kline", value, ttl_seconds=3600)
                    result["kline"] = value
                else:
                    logger.warning("K线数据为空: %s", code)
            elif label == "benchmark_kline":
                if not value.empty:
                    c.set("benchmark_kline", value, ttl_seconds=3600)
                    result["benchmark_kline"] = value
                else:
                    logger.warning("沪深300 K线数据为空")
            elif label == "industry_pe":
                if value:
                    c.set(f"{code}:industry_pe", value, ttl_seconds=86_400)
                    result["industry_pe"] = value
            elif label == "quarterly_income":
                c.set(f"{code}:quarterly_income", value)
                result["quarterly_income"] = value
            elif label == "macro_indicators":
                c.set("macro_indicators", value, ttl_seconds=86_400)
                result["macro_indicators"] = value
            elif label == "news_list":
                c.set(f"{code}:news", value, ttl_seconds=3600)
                result["news_list"] = value

    # ── Step 2: 依赖 industry_info 的串行调用 ──
    # 关键非财务事件（需要股票名称）
    with open_span("data_source:akshare:key_events", input={"code": code}) as obs:
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
            if obs:
                obs.update(output={"status": "success", "count": len(events)})
        except Exception as e:
            if obs:
                obs.update(output={"status": "error", "error": str(e)}, level="ERROR")
            logger.warning("关键事件获取失败: %s", e)
            result["key_events"] = []

    # 同业数据（依赖行业归属）
    with open_span("data_source:akshare:peer_financials", input={"code": code}) as obs:
        try:
            peers = _fetch_peers(ak, code, state, result.get("industry_info"))
            if peers is not None:
                result["peer_financials"] = peers
                if obs:
                    obs.update(output=_summarize_success_output(peers))
            else:
                if obs:
                    obs.update(output={"status": "skipped", "reason": "无同业代码"})
        except Exception as e:
            if obs:
                obs.update(output={"status": "error", "error": str(e)}, level="ERROR")
            logger.warning("同业数据拉取失败: %s", e)
            result["peer_financials"] = None

    return result


def _fetch_peers(ak, code, state, industry_info):
    peer_codes = state.get("peer_codes")
    if not peer_codes or not industry_info:
        return None
    return ak.fetch_peer_data(peer_codes)
