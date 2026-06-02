"""运营效率 4 指标计算。

指标：
1. 存货周转率（次）— AKShare 预计算（年报）
2. 应收账款周转率（次）— 营业收入 / 应收账款平均余额（自算）
3. 总资产周转率（次）— 营业收入 / 资产总计
4. 应付账款周转率（次）— 营业成本 / 应付账款
"""

from __future__ import annotations

import pandas as pd


def _year(date_str: str) -> str:
    return str(date_str)[:4]


def _safe(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return float(val)


def calc_efficiency(
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    indicators: pd.DataFrame,
) -> dict[str, dict[str, float | None]]:
    years = [_year(d) for d in income_statement["报告日"]]
    result: dict[str, dict[str, float | None]] = {
        "存货周转率": {},
        "应收账款周转率": {},
        "总资产周转率": {},
        "应付账款周转率": {},
    }

    for i, year in enumerate(years):
        row_is = income_statement.iloc[i]
        row_bs = balance_sheet.iloc[i]

        revenue = _safe(row_is.get("营业收入"))
        cost = _safe(row_is.get("营业成本"))
        total_assets = _safe(row_bs.get("资产总计"))
        accounts_payable = _safe(row_bs.get("应付账款"))

        # 从 indicators 取存货周转率（如果 balance sheet 没有）
        ind_val = indicators.iloc[i] if indicators is not None and i < len(indicators) else None
        if ind_val is not None:
            val = ind_val.get("存货周转率(次)")
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                result["存货周转率"][year] = float(val)
            else:
                result["存货周转率"][year] = None
        else:
            result["存货周转率"][year] = None

        # 应收账款周转率 — 自算: 营业收入 / 应收账款
        # 数据最新在前：i+1 是上一年，用年初+年末均值
        accounts_receivable = _safe(row_bs.get("应收账款"))
        if i < len(years) - 1:
            prev_ar = _safe(balance_sheet.iloc[i + 1].get("应收账款"))
            avg_ar = (accounts_receivable + prev_ar) / 2
        else:
            avg_ar = accounts_receivable
        if avg_ar != 0:
            result["应收账款周转率"][year] = revenue / avg_ar
        else:
            result["应收账款周转率"][year] = None

        # 总资产周转率 — 自算
        if total_assets != 0:
            result["总资产周转率"][year] = revenue / total_assets
        else:
            result["总资产周转率"][year] = None

        # 应付账款周转率 — 自算
        if accounts_payable != 0:
            result["应付账款周转率"][year] = cost / accounts_payable
        else:
            result["应付账款周转率"][year] = None

    return result
