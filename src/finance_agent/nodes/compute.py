"""compute_metrics: 编排全部 metrics/ 模块，写入 State Layer 3 字段。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from finance_agent.metrics.cashflow import calc_cashflow
from finance_agent.metrics.dupont import calc_dupont
from finance_agent.metrics.efficiency import calc_efficiency
from finance_agent.metrics.garp import calc_garp
from finance_agent.metrics.profitability import calc_profitability
from finance_agent.metrics.relative import calc_relative_valuation
from finance_agent.metrics.solvency import calc_solvency
from finance_agent.metrics.traffic_light import assess_traffic_lights, compute_health_score
from finance_agent.state import AnalysisState


def compute_metrics(state: AnalysisState) -> dict[str, Any]:
    bs = state["balance_sheet"]
    inc = state["income_statement"]
    cf = state["cash_flow_statement"]
    ind = state.get("financial_indicators")

    result: dict = {}

    # ── 四维度指标 ──
    solvency = calc_solvency(bs, inc, ind)
    profitability = calc_profitability(bs, inc, ind)
    efficiency = calc_efficiency(bs, inc, ind)
    cashflow = calc_cashflow(bs, inc, cf)

    result["solvency_metrics"] = solvency
    result["profitability_metrics"] = profitability
    result["efficiency_metrics"] = efficiency
    result["cashflow_metrics"] = cashflow

    # ── 杜邦 ──
    result["dupont_tree"] = calc_dupont(bs, inc)

    # ── 红黄绿灯 + 评分 ──
    all_metrics = {
        "solvency": solvency,
        "profitability": profitability,
        "efficiency": efficiency,
        "cashflow": cashflow,
    }
    industry = (state.get("industry_info") or {}).get("industry")
    traffic_lights = assess_traffic_lights(all_metrics, industry=industry)
    result["traffic_lights"] = traffic_lights

    years = sorted(
        {y for dim in all_metrics.values() for v in dim.values() for y in v},
        reverse=True,
    )
    latest_year = years[0] if years else None
    if latest_year:
        result["health_score"] = compute_health_score(traffic_lights, latest_year)

    # ── 增长率 ──
    result["growth_rates"] = _calc_growth_rates(all_metrics, years)

    # ── 异常检测 ──
    result["anomalies"] = _detect_anomalies(traffic_lights, result["growth_rates"], latest_year)

    # ── 相对估值（需要同业数据）──
    peer_financials = state.get("peer_financials")
    quote = state.get("stock_quote") or {}
    if peer_financials is not None and quote:
        pe = quote.get("PE") or quote.get("pe")
        pb = quote.get("PB") or quote.get("pb")
        if pe is not None or pb is not None:
            target = {"PE": pe, "PB": pb}
            peers_list = _build_peers_list(peer_financials)
            if peers_list:
                result["relative_valuation"] = calc_relative_valuation(target, peers_list)

    # ── 净利润增长率（用于 GARP）──
    net_profit_growth = _calc_net_profit_growth(inc, latest_year, years)

    # ── GARP（需要估值数据）──
    result["garp_result"] = _try_garp(
        quote, profitability, solvency, ind, net_profit_growth, latest_year
    )

    # ── 同业对比（如果有 peer 数据）──
    # TODO(Issue #4): peer_comparison 目前仅是标志位，需添加同业指标格式化器注入 LLM context
    if peer_financials is not None:
        result["peer_comparison"] = {"available": True}

    return result


def _calc_growth_rates(
    all_metrics: dict[str, dict],
    years: list[str],
) -> dict[str, dict[str, float | None]]:
    if len(years) < 2:
        return {}
    latest, prev = years[0], years[1]
    growth: dict[str, dict[str, float | None]] = {}
    for dim_name, dim_metrics in all_metrics.items():
        for metric_name, year_values in dim_metrics.items():
            v_new = year_values.get(latest)
            v_old = year_values.get(prev)
            if v_new is not None and v_old is not None and v_old != 0:
                rate = (v_new - v_old) / abs(v_old)
            else:
                rate = None
            growth.setdefault(dim_name, {})[metric_name] = rate
    return growth


def _detect_anomalies(
    traffic_lights: dict,
    growth_rates: dict,
    latest_year: str | None,
) -> list[str]:
    anomalies: list[str] = []
    if not latest_year:
        return anomalies
    for dim_name, dim_metrics in traffic_lights.items():
        for metric_name, year_data in dim_metrics.items():
            entry = year_data.get(latest_year, {})
            if entry.get("final") == "red":
                anomalies.append(f"{dim_name}.{metric_name}: 红灯")
            growth = growth_rates.get(dim_name, {}).get(metric_name)
            if growth is not None and abs(growth) > 0.50:
                anomalies.append(f"{dim_name}.{metric_name}: 变化率{growth:.0%}")
    return anomalies


def _build_peers_list(peer_financials) -> list[dict]:
    import pandas as pd

    if not isinstance(peer_financials, pd.DataFrame) or peer_financials.empty:
        return []
    peers = []
    for _, row in peer_financials.iterrows():
        p = {"name": row.get("name", row.get("股票名称", ""))}
        for k in ("PE", "PB", "pe", "pb"):
            v = row.get(k)
            if v is not None:
                p[k.upper()] = v
        peers.append(p)
    return peers


def _calc_net_profit_growth(
    income_statement: pd.DataFrame,
    latest_year: str | None,
    years: list[str],
) -> float | None:
    """计算归母净利润的同比增长率（用于 GARP）。"""
    if not latest_year or len(years) < 2:
        return None
    prev_year = years[1] if years[0] == latest_year else None
    if not prev_year:
        return None

    def _get_np(df: pd.DataFrame, year: str) -> float | None:
        mask = df["报告日"].astype(str).str.startswith(year)
        rows = df[mask]
        if rows.empty:
            return None
        # 优先使用归母净利润，回退到合并净利润
        val = rows.iloc[0].get("归母净利润") or rows.iloc[0].get("净利润")
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)

    latest_np = _get_np(income_statement, latest_year)
    prev_np = _get_np(income_statement, prev_year)
    if latest_np is not None and prev_np is not None and prev_np != 0:
        return (latest_np - prev_np) / abs(prev_np)
    return None


def _try_garp(
    quote,
    profitability,
    solvency,
    indicators,
    net_profit_growth: float | None,
    latest_year: str | None,
) -> dict | None:
    pe = (quote or {}).get("PE") or (quote or {}).get("pe")
    industry_pe = (quote or {}).get("industry_avg_PE")
    if not latest_year:
        return None
    roe = profitability.get("ROE", {}).get(latest_year)
    # 负债率从百分比转为小数（如 16.42 → 0.1642）
    debt_pct = solvency.get("资产负债率", {}).get(latest_year)
    debt = debt_pct / 100 if debt_pct is not None else None
    data = {
        "PE": pe,
        "industry_avg_PE": industry_pe,
        "net_profit_growth": net_profit_growth,
        "ROE": roe,
        "debt_ratio": debt,
    }
    return calc_garp(data)
