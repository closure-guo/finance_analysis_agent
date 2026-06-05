"""现金流健康 6 指标计算。

指标：
1. 经营现金流/净利润 — OCF / 归母净利润（缺失时回退合并净利润）
2. FCF — OCF - CapEx
3. 资本支出/折旧 — CapEx / 折旧变动
4. 现金流覆盖比率 — FCF / (CapEx + 利息费用)
5. FCF收益率 — FCF / 营业收入（MVP 简化，v2.0 改用市值）
6. 留存现金流比率 — (FCF - 股利支付) / FCF
"""

from __future__ import annotations

import pandas as pd


def _year(date_str: str) -> str:
    return str(date_str)[:4]


def _safe(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return float(val)


def calc_cashflow(
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    cash_flow: pd.DataFrame,
) -> dict[str, dict[str, float | None]]:
    years = [_year(d) for d in cash_flow["报告日"]]
    n = len(years)
    result: dict[str, dict[str, float | None]] = {
        "经营现金流/净利润": {},
        "FCF": {},
        "资本支出/折旧": {},
        "现金流覆盖比率": {},
        "FCF收益率": {},
        "留存现金流比率": {},
    }

    for i in range(n):
        year = years[i]
        row_cf = cash_flow.iloc[i]
        row_is = income_statement.iloc[i]
        row_bs = balance_sheet.iloc[i]

        ocf = _safe(row_cf.get("经营活动产生的现金流量净额"))
        capex = _safe(row_cf.get("购建固定资产、无形资产和其他长期资产所支付的现金"))
        dividends = _safe(row_cf.get("分配股利、利润或偿付利息所支付的现金"))
        # 使用归母净利润口径，与 profitability/dupont 保持一致
        net_income = _safe(row_is.get("归母净利润"))
        if net_income == 0:
            net_income = _safe(row_is.get("净利润"))
        interest = _safe(row_is.get("利息费用"))
        revenue = _safe(row_is.get("营业收入"))
        depreciation = _safe(row_bs.get("累计折旧"))

        # 折旧变动：数据最新在前，i+1 是上一年
        dep_change = 0.0
        if i < n - 1:
            prev_dep = _safe(balance_sheet.iloc[i + 1].get("累计折旧"))
            dep_change = depreciation - prev_dep

        fcf = ocf - capex

        # 经营现金流/净利润
        if net_income != 0:
            result["经营现金流/净利润"][year] = ocf / net_income
        else:
            result["经营现金流/净利润"][year] = None

        # FCF
        result["FCF"][year] = fcf

        # 资本支出/折旧
        if dep_change != 0:
            result["资本支出/折旧"][year] = capex / dep_change
        else:
            result["资本支出/折旧"][year] = None

        # 现金流覆盖比率
        denominator = capex + interest
        if denominator != 0:
            result["现金流覆盖比率"][year] = fcf / denominator
        else:
            result["现金流覆盖比率"][year] = None

        # FCF收益率（MVP 用营业收入代替市值）
        if revenue != 0:
            result["FCF收益率"][year] = fcf / revenue
        else:
            result["FCF收益率"][year] = None

        # 留存现金流比率
        if fcf != 0:
            result["留存现金流比率"][year] = (fcf - dividends) / fcf
        else:
            result["留存现金流比率"][year] = None

    return result
