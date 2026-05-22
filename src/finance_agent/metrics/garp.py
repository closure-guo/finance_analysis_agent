"""GARP 筛选 — Growth at a Reasonable Price。

条件（全部严格满足）：
- PE < 行业平均
- 净利润增长率 > 15%
- ROE > 15%
- 负债率 < 60%
"""

from __future__ import annotations


def calc_garp(data: dict) -> dict:
    """执行 GARP 筛选。

    Parameters
    ----------
    data : dict
        PE, industry_avg_PE, net_profit_growth, ROE, debt_ratio

    Returns
    -------
    dict
        {"pass": bool, "failures": [str], "details": dict}
    """
    failures = []
    details = {}

    pe = data.get("PE")
    industry_pe = data.get("industry_avg_PE")
    growth = data.get("net_profit_growth")
    roe = data.get("ROE")
    debt = data.get("debt_ratio")

    if pe is None or industry_pe is None:
        failures.append("PE >= 行业平均")
        details["PE"] = None
    elif pe >= industry_pe:
        failures.append("PE >= 行业平均")
        details["PE"] = pe
    else:
        details["PE"] = pe

    if growth is None:
        failures.append("净利润增长率 <= 15%")
        details["净利润增长率"] = None
    elif growth <= 0.15:
        failures.append("净利润增长率 <= 15%")
        details["净利润增长率"] = growth
    else:
        details["净利润增长率"] = growth

    if roe is None:
        failures.append("ROE <= 15%")
        details["ROE"] = None
    elif roe <= 0.15:
        failures.append("ROE <= 15%")
        details["ROE"] = roe
    else:
        details["ROE"] = roe

    if debt is None:
        failures.append("负债率 >= 60%")
        details["负债率"] = None
    elif debt >= 0.60:
        failures.append("负债率 >= 60%")
        details["负债率"] = debt
    else:
        details["负债率"] = debt

    return {
        "pass": len(failures) == 0,
        "failures": failures,
        "details": details,
    }
