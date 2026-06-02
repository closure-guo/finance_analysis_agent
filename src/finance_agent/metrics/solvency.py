"""偿债能力 5 指标计算。

指标：
1. 资产负债率（%）— 负债合计 / 资产总计
2. 流动比率（x）— 流动资产合计 / 流动负债合计
3. 速动比率（x）— (流动资产合计 - 存货) / 流动负债合计
4. 利息覆盖倍数（x）— EBIT / 利息费用 = (利润总额 + 利息费用) / 利息费用
5. 净债务/EBITDA（x）— 有息负债 - 货币资金) / EBITDA

输入为 AKShare 格式的 DataFrame，输出 {指标名: {年份: 值}}。
"""

from __future__ import annotations

import pandas as pd


def _year_from_report_date(date_str: str) -> str:
    """从 '20241231' 格式提取年份 '2024'。"""
    return str(date_str)[:4]


def _safe_num(val) -> float:
    """安全提取数值，将 None/NaN 转为 0.0。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    return float(val)


def _is_valid(val: object) -> bool:
    """判断数值是否有效（非 None、非 NaN、非 0）。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return val != 0


def calc_solvency(
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    indicators: pd.DataFrame | None,
) -> dict[str, dict[str, float | None]]:
    """计算偿债能力 5 指标。

    Parameters
    ----------
    balance_sheet : DataFrame
        AKShare 资产负债表，需含 报告日/资产总计/负债合计/流动资产合计/流动负债合计/存货/货币资金
        /短期借款/长期借款/应付债券/一年内到期的非流动负债/累计折旧 等列。
    income_statement : DataFrame
        AKShare 利润表，需含 报告日/利润总额/利息费用 等列。
    indicators : DataFrame
        AKShare 预计算指标（部分指标备用）。

    Returns
    -------
    dict
        {指标名: {年份: 值}}
    """
    years = [_year_from_report_date(d) for d in balance_sheet["报告日"]]

    result: dict[str, dict[str, float | None]] = {
        "资产负债率": {},
        "流动比率": {},
        "速动比率": {},
        "利息覆盖倍数": {},
        "净债务/EBITDA": {},
    }

    n = len(years)
    for i in range(n):
        year = years[i]

        # ── 从资产负债表取值 ──
        total_assets = balance_sheet.iloc[i].get("资产总计")
        total_liabilities = balance_sheet.iloc[i].get("负债合计")
        current_assets = balance_sheet.iloc[i].get("流动资产合计")
        current_liabilities = balance_sheet.iloc[i].get("流动负债合计")
        inventory = balance_sheet.iloc[i].get("存货")
        cash = _safe_num(balance_sheet.iloc[i].get("货币资金"))
        short_debt = _safe_num(balance_sheet.iloc[i].get("短期借款"))
        long_debt = _safe_num(balance_sheet.iloc[i].get("长期借款"))
        bonds = _safe_num(balance_sheet.iloc[i].get("应付债券"))
        current_ncl = _safe_num(balance_sheet.iloc[i].get("一年内到期的非流动负债"))
        depreciation = _safe_num(balance_sheet.iloc[i].get("累计折旧"))

        # ── 从利润表取值 ──
        profit_before_tax = income_statement.iloc[i].get("利润总额")
        interest_expense = income_statement.iloc[i].get("利息费用")

        # ── 资产负债率 (%) ──
        if _is_valid(total_assets) and _is_valid(total_liabilities):
            result["资产负债率"][year] = float(total_liabilities / total_assets * 100)
        else:
            result["资产负债率"][year] = None

        # ── 流动比率 ──
        if _is_valid(current_assets) and _is_valid(current_liabilities):
            result["流动比率"][year] = float(current_assets / current_liabilities)
        else:
            result["流动比率"][year] = None

        # ── 速动比率 ──
        if (
            _is_valid(current_assets)
            and inventory is not None
            and _is_valid(current_liabilities)
            and not (isinstance(inventory, float) and pd.isna(inventory))
        ):
            result["速动比率"][year] = float((current_assets - inventory) / current_liabilities)
        else:
            result["速动比率"][year] = None

        # ── 利息覆盖倍数 ──
        if (
            _is_valid(interest_expense)
            and profit_before_tax is not None
            and not (isinstance(profit_before_tax, float) and pd.isna(profit_before_tax))
        ):
            ebit = profit_before_tax + interest_expense
            result["利息覆盖倍数"][year] = float(ebit / interest_expense)
        else:
            result["利息覆盖倍数"][year] = None

        # ── 净债务/EBITDA ──
        interest_bearing_debt = short_debt + long_debt + bonds + current_ncl
        net_debt = interest_bearing_debt - cash

        # EBITDA = 利润总额 + 利息费用 + 折旧变动
        # 数据最新在前：i+1 是上一年
        depreciation_change = 0.0
        if i < n - 1:
            prev_dep = _safe_num(balance_sheet.iloc[i + 1].get("累计折旧"))
            depreciation_change = depreciation - prev_dep
        else:
            # 最老年份没有同比折旧，设为 0
            depreciation_change = 0.0

        pbt = _safe_num(profit_before_tax)
        ie = _safe_num(interest_expense)
        ebitda = pbt + ie + depreciation_change

        if ebitda != 0:
            result["净债务/EBITDA"][year] = float(net_debt / ebitda)
        else:
            result["净债务/EBITDA"][year] = None

    return result
