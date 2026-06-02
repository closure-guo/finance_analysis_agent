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
        net_income = _safe(row_is.get("净利润"))
        profit_before_tax = _safe(row_is.get("利润总额"))
        tax = _safe(row_is.get("所得税费用"))
        interest = _safe(row_is.get("利息费用"))
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

        # ROE
        if equity != 0:
            result["ROE"][year] = net_income / equity * 100
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
