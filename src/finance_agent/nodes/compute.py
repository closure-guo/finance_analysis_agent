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
from finance_agent.metrics.risk import calc_risk
from finance_agent.metrics.solvency import calc_solvency
from finance_agent.metrics.technical import calc_technical
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
    # 保留 source 标注，但 all_metrics 只含数值指标
    efficiency_numeric = {k: v for k, v in efficiency.items() if not k.endswith("_source")}

    all_metrics = {
        "solvency": solvency,
        "profitability": profitability,
        "efficiency": efficiency_numeric,
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
    growth = _calc_growth_rates(all_metrics, years)

    # 补算营收和净利润绝对值增长率，避免 LLM 自行计算
    if len(years) >= 2:
        _append_absolute_growth(growth, inc, years, "营业收入", "profitability")
        _append_absolute_growth(growth, inc, years, "归母净利润", "profitability")
        _append_absolute_growth(
            growth, inc, years, "净利润", "profitability", fallback_col="归母净利润"
        )

    result["growth_rates"] = growth

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

    # ── 季度趋势 ──
    q_income = state.get("quarterly_income")
    if q_income is not None and not q_income.empty:
        result["quarterly_trend"] = _calc_quarterly_trend(q_income)

    # ── 同业对比（如果有 peer 数据）──
    # TODO(Issue #4): peer_comparison 目前仅是标志位，需添加同业指标格式化器注入 LLM context
    if peer_financials is not None:
        result["peer_comparison"] = {"available": True}

    # ── 技术指标 + 风控指标（需要 K 线数据）──
    kline = state.get("kline")
    if kline is not None and not kline.empty:
        result["technical_indicators"] = calc_technical(kline)
        benchmark = state.get("benchmark_kline")
        result["risk_metrics"] = calc_risk(kline, benchmark)

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


def _append_absolute_growth(
    growth: dict[str, dict[str, float | None]],
    income_statement: pd.DataFrame,
    years: list[str],
    col_name: str,
    dim_name: str,
    fallback_col: str | None = None,
) -> None:
    """从利润表取绝对值计算同比增长率，追加到 growth dict。"""
    latest, prev = years[0], years[1]

    def _get_val(year: str) -> float | None:
        mask = income_statement["报告日"].astype(str).str.startswith(year)
        rows = income_statement[mask]
        if rows.empty:
            return None
        v = rows.iloc[0].get(col_name)
        if (v is None or (isinstance(v, float) and pd.isna(v))) and fallback_col:
            v = rows.iloc[0].get(fallback_col)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)

    v_new = _get_val(latest)
    v_old = _get_val(prev)
    if v_new is not None and v_old is not None and v_old != 0:
        growth.setdefault(dim_name, {})[col_name] = (v_new - v_old) / abs(v_old)


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


def _calc_quarterly_trend(q_income: pd.DataFrame) -> dict:
    """计算季度趋势：同比/环比序列 + 拐点检测。"""
    if q_income.empty or "归母净利润(单季)" not in q_income.columns:
        return {}

    trend: dict = {
        "quarters": [],
        "net_profit": [],
        "qoq": [],
        "yoy": [],
        "warnings": [],
    }

    for _, row in q_income.iterrows():
        trend["quarters"].append(row.get("季度", ""))
        np_val = row.get("归母净利润(单季)")
        trend["net_profit"].append(round(np_val / 1e8, 2) if pd.notna(np_val) else None)
        qoq = row.get("环比")
        trend["qoq"].append(qoq)
        yoy = row.get("同比")
        trend["yoy"].append(yoy)

    # 拐点检测
    yoy_vals = [v for v in trend["yoy"] if v is not None]
    q_vals = trend["quarters"]
    if yoy_vals:
        # 1. 最近季度同比为负或大幅下降
        if yoy_vals[0] < -20:
            trend["warnings"].append(
                f"最近季度 ({q_vals[0]}) 归母净利润同比大幅下降 {yoy_vals[0]:.1f}%"
            )
        elif yoy_vals[0] < 0:
            trend["warnings"].append(
                f"最近季度 ({q_vals[0]}) 归母净利润同比下降 {yoy_vals[0]:.1f}%"
            )

        # 2. 最近 4 个季度中存在同比大幅下降（即使不是最近季度）
        for i, yoy in enumerate(yoy_vals):
            if yoy is not None and yoy < -20 and i > 0:
                trend["warnings"].append(f"{q_vals[i]} 归母净利润同比大幅下降 {yoy:.1f}%")
                break  # 只报告第一个历史大幅下降

        # 3. 连续两个季度同比下降
        if len(yoy_vals) >= 2 and yoy_vals[0] < 0 and yoy_vals[1] < 0:
            trend["warnings"].append(
                f"连续两个季度同比下降 ({q_vals[0]}: {yoy_vals[0]:.1f}%, "
                f"{q_vals[1]}: {yoy_vals[1]:.1f}%)"
            )

    return trend
