"""杜邦 3 层分解。

L1: ROE = 净利率 × 总资产周转率 × 权益乘数
L2: 净利率拆解（毛利率 - 费用率）；周转率拆解（资产构成）；权益乘数拆解（负债结构）
L3: 费用率细分（销售/管理/研发/财务费用率）
"""

from __future__ import annotations

import pandas as pd


def _year(date_str: str) -> str:
    return str(date_str)[:4]


def _safe(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return float(val)


def calc_dupont(
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
) -> dict[str, dict[str, dict]]:
    years = [_year(d) for d in income_statement["报告日"]]
    result = {"L1": {}, "L2": {}, "L3": {}}

    for i, year in enumerate(years):
        row_is = income_statement.iloc[i]
        row_bs = balance_sheet.iloc[i]

        revenue = _safe(row_is.get("营业收入"))
        cost = _safe(row_is.get("营业成本"))
        net_income = _safe(row_is.get("净利润"))
        total_assets = _safe(row_bs.get("资产总计"))
        equity = _safe(row_bs.get("所有者权益(或股东权益)合计"))
        sales_exp = _safe(row_is.get("销售费用"))
        admin_exp = _safe(row_is.get("管理费用"))
        rd_exp = _safe(row_is.get("研发费用"))
        finance_exp = _safe(row_is.get("财务费用"))

        # L1: ROE = 净利率 × 总资产周转率 × 权益乘数
        net_margin = net_income / revenue if revenue != 0 else 0
        asset_turnover = revenue / total_assets if total_assets != 0 else 0
        equity_multiplier = total_assets / equity if equity != 0 else 0
        roe = net_margin * asset_turnover * equity_multiplier

        result["L1"][year] = {
            "ROE": roe,
            "净利率": net_margin,
            "总资产周转率": asset_turnover,
            "权益乘数": equity_multiplier,
        }

        # L2: 净利率拆解
        gross_margin = (revenue - cost) / revenue if revenue != 0 else 0
        total_expense_rate = (
            (sales_exp + admin_exp + rd_exp + finance_exp) / revenue if revenue != 0 else 0
        )

        result["L2"][year] = {
            "毛利率": gross_margin,
            "费用率": total_expense_rate,
        }

        # L3: 费用率细分
        result["L3"][year] = {
            "销售费用率": sales_exp / revenue if revenue != 0 else 0,
            "管理费用率": admin_exp / revenue if revenue != 0 else 0,
            "研发费用率": rd_exp / revenue if revenue != 0 else 0,
            "财务费用率": finance_exp / revenue if revenue != 0 else 0,
        }

    return result
