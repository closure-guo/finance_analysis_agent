"""GARP 筛选 — Growth at a Reasonable Price。

条件（全部严格满足）：
- PE < 行业平均
- 净利润增长率 > 15%
- ROE > 15%
- 负债率 < 60%
"""

from __future__ import annotations


def _clean_num(v) -> float | None:
    """NaN 视同缺失：NaN 参与比较恒 False，会把缺数伪装成比较通过。

    v != v 为 IEEE NaN 判定，类型无关——np.float32 等 numpy 标量（非 float
    子类）同样命中，不再被 isinstance 守卫漏过（终审 nit）。
    """
    if v is None:
        return None
    if v != v:
        return None
    return float(v)


def calc_garp(data: dict) -> dict:
    """执行 GARP 筛选。

    Parameters
    ----------
    data : dict
        PE, industry_avg_PE, net_profit_growth, ROE, debt_ratio, PE_caliber(可选)

    Returns
    -------
    dict
        {"pass": bool, "failures": [str], "details": dict}
    """
    failures: list[str] = []
    details: dict[str, float | None | bool | str] = {}

    pe = _clean_num(data.get("PE"))
    industry_pe = _clean_num(data.get("industry_avg_PE"))
    caliber = data.get("PE_caliber")
    growth = _clean_num(data.get("net_profit_growth"))
    roe = _clean_num(data.get("ROE"))
    debt = _clean_num(data.get("debt_ratio"))

    if pe is None:
        # 数据缺失 ≠ 比较失败：缺输入不得谎报比较结论（诚实分桶）
        failures.append("PE 数据缺失（未参与比较）")
        details["PE"] = None
        details["PE_missing"] = True
    elif industry_pe is None:
        failures.append("行业平均 PE 数据缺失（未参与比较）")
        details["PE"] = pe
        details["PE_missing"] = True
        details["PE_caliber"] = caliber
    elif pe >= industry_pe:
        failures.append("PE >= 行业平均")
        details["PE"] = pe
        details["PE_caliber"] = caliber
    else:
        details["PE"] = pe
        details["PE_caliber"] = caliber

    if growth is None:
        # 数据缺失 ≠ 比较失败（D1：与 PE 同款诚实分桶）
        failures.append("净利润增长率 数据缺失（未参与比较）")
        details["净利润增长率"] = None
        details["净利润增长率_missing"] = True
    elif growth <= 0.15:
        failures.append("净利润增长率 <= 15%")
        details["净利润增长率"] = growth
    else:
        details["净利润增长率"] = growth

    if roe is None:
        # 数据缺失 ≠ 比较失败（D1：与 PE 同款诚实分桶）
        failures.append("ROE 数据缺失（未参与比较）")
        details["ROE"] = None
        details["ROE_missing"] = True
    elif roe <= 0.15:
        failures.append("ROE <= 15%")
        details["ROE"] = roe
    else:
        details["ROE"] = roe

    if debt is None:
        # 数据缺失 ≠ 比较失败（D1：与 PE 同款诚实分桶）
        failures.append("负债率 数据缺失（未参与比较）")
        details["负债率"] = None
        details["负债率_missing"] = True
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
