"""盈利能力 5 指标计算。

指标：
1. 毛利率（%）— (营业收入 - 营业成本) / 营业收入
2. 净利率（%）— 净利润 / 营业收入
3. ROE（%）— 净利润 / 所有者权益
4. ROA（%）— 净利润 / 资产总计
5. ROIC（%）— NOPAT / 投入资本
   NOPAT = EBIT × (1 - 税率), 税率 = 所得税/利润总额
   投入资本 = 所有者权益 + 有息负债
"""

from __future__ import annotations

import pandas as pd

from finance_agent.metrics.efficiency import _find_indicator


def _year(date_str: str) -> str:
    return str(date_str)[:4]


def _safe(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return float(val)


def calc_profitability(
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    indicators: pd.DataFrame | None,
) -> dict[str, dict[str, float | None]]:
    years = [_year(d) for d in income_statement["报告日"]]
    result: dict[str, dict[str, float | None]] = {
        "毛利率": {},
        "净利率": {},
        "ROE": {},
        "ROA": {},
        "ROIC": {},
    }

    n = len(years)
    for i in range(n):
        year = years[i]
        row_is = income_statement.iloc[i]
        row_bs = balance_sheet.iloc[i]

        revenue = _safe(row_is.get("营业收入"))
        cost = _safe(row_is.get("营业成本"))
        # 使用归母净利润口径（投资者关注的核心指标）
        net_income = _safe(row_is.get("归母净利润"))
        # 回退：如果归母净利润缺失，使用合并净利润
        if net_income == 0:
            net_income = _safe(row_is.get("净利润"))
        profit_before_tax = _safe(row_is.get("利润总额"))
        tax = _safe(row_is.get("所得税费用"))
        interest = _safe(row_is.get("利息费用"))
        # ROE 分母使用归母权益；回退到所有者权益合计
        equity = _safe(row_bs.get("归母所有者权益"))
        if equity == 0:
            equity = _safe(row_bs.get("所有者权益(或股东权益)合计"))
        short_debt = _safe(row_bs.get("短期借款"))
        long_debt = _safe(row_bs.get("长期借款"))
        bonds = _safe(row_bs.get("应付债券"))
        current_ncl = _safe(row_bs.get("一年内到期的非流动负债"))

        # 毛利率
        if revenue != 0:
            result["毛利率"][year] = (revenue - cost) / revenue * 100
        else:
            result["毛利率"][year] = None

        # 净利率
        if revenue != 0:
            result["净利率"][year] = net_income / revenue * 100
        else:
            result["净利率"][year] = None

        # ROE — 优先用 indicators 加权净资产收益率（证监会口径）
        ind_row = _find_indicator(indicators, year)
        weighted_roe = None
        if ind_row is not None:
            val = ind_row.get("加权净资产收益率(%)")
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                weighted_roe = float(val)

        if weighted_roe is not None:
            result["ROE"][year] = weighted_roe
        else:
            # fallback: 归母净利润 / 平均归母权益
            avg_equity = equity
            if i < len(years) - 1:
                prev_row_bs = balance_sheet.iloc[i + 1]
                prev_equity = _safe(prev_row_bs.get("归母所有者权益"))
                if prev_equity == 0:
                    prev_equity = _safe(prev_row_bs.get("所有者权益(或股东权益)合计"))
                if prev_equity != 0:
                    avg_equity = (equity + prev_equity) / 2
            if avg_equity != 0:
                result["ROE"][year] = net_income / avg_equity * 100
            else:
                result["ROE"][year] = None

        # ROA
        total_assets = _safe(row_bs.get("资产总计"))
        if total_assets != 0:
            result["ROA"][year] = net_income / total_assets * 100
        else:
            result["ROA"][year] = None

        # ROIC
        ebit = profit_before_tax + interest
        tax_rate = tax / profit_before_tax if profit_before_tax != 0 else 0
        nopat = ebit * (1 - tax_rate)
        invested_capital = equity + short_debt + long_debt + bonds + current_ncl
        if invested_capital != 0:
            result["ROIC"][year] = nopat / invested_capital * 100
        else:
            result["ROIC"][year] = None

    return result
