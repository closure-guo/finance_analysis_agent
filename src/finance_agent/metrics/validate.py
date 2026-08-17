"""勾稽校验 — 三大报表内在一致性验证。

ADR-0005 实现：
- 规则1：试算平衡（硬等式）— 资产总计 = 负债合计 + 所有者权益合计
- 规则2：利润表内部勾稽（软等式）— 收入-成本-费用 ≈ 营业利润
- 规则3：现金流量表内部勾稽（软等式）— 经营+投资+筹资 = 现金净变动
- 规则4：留存收益勾稽（软等式）— 期末留存 = 期初留存 + 净利润 - 分红
"""

from __future__ import annotations

import pandas as pd

# ── 阈值 ──
HARD_TOLERANCE_PCT = 0.01  # 硬等式：相对误差 < 0.01%
SOFT_TOLERANCE_PCT = 0.05  # 软等式：相对误差 < 5%
SOFT_TOLERANCE_ABS = 1_000_000.0  # 软等式：绝对值兜底 100万


def _year(date_str: str) -> str:
    return str(date_str)[:4]


def _safe(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return float(val)


def _equity_total(row) -> float:
    """从资产负债表行推导所有者权益合计（兼容银行等无该列的结构）。

    优先标准列；银行表无「所有者权益(或股东权益)合计」，但有
    「负债及股东权益总计」——用 总计 - 负债 推导（恒等式 资产=负债+权益）。
    最后兜底 归母所有者权益 + 少数股东权益。均缺失返回 0（保持旧行为）。
    """
    for col in ("所有者权益(或股东权益)合计", "所有者权益合计", "股东权益合计"):
        v = row.get(col)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            return float(v)
    balance_total = row.get("负债及股东权益总计")
    liabilities = row.get("负债合计")
    if balance_total is not None and liabilities is not None:
        return float(balance_total) - float(liabilities)
    parent = row.get("归母所有者权益") or row.get("归属于母公司股东的权益")
    minority = row.get("少数股东权益")
    if parent is not None:
        return float(parent) + (float(minority) if minority is not None else 0.0)
    return 0.0


def _soft_threshold(base: float) -> float:
    """软等式阈值：max(基准值 × 5%, 100万)。"""
    return max(abs(base) * SOFT_TOLERANCE_PCT, SOFT_TOLERANCE_ABS)


def validate_financials(
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    cash_flow: pd.DataFrame,
) -> dict:
    """执行4条勾稽校验规则。

    Returns
    -------
    dict
        {"result": "PASS" | "FAIL", "warnings": list[str], "details": list[str]}
    """
    warnings: list[str] = []
    details: list[str] = []
    result = "PASS"

    # ── 规则1：试算平衡（硬等式）──
    for _i, row in balance_sheet.iterrows():
        year = _year(row["报告日"])
        assets = _safe(row.get("资产总计"))
        liabilities = _safe(row.get("负债合计"))
        equity = _equity_total(row)

        if assets <= 0:
            details.append(f"[{year}] 规则1跳过：资产总计为空或<=0")
            continue

        expected_assets = liabilities + equity
        diff = abs(assets - expected_assets)
        diff_pct = diff / assets * 100

        if diff_pct >= HARD_TOLERANCE_PCT:
            result = "FAIL"
            msg = (
                f"[{year}] 试算平衡失败（硬等式）："
                f"资产={assets:,.0f}，负债+权益={expected_assets:,.0f}，"
                f"差异={diff:,.0f}（{diff_pct:.4f}% >= {HARD_TOLERANCE_PCT}%）"
            )
            warnings.append(msg)
            details.append(msg)
        else:
            details.append(f"[{year}] 试算平衡通过：差异={diff:,.0f}（{diff_pct:.4f}%）")

    # ── 规则2：利润表内部勾稽（软等式）──
    # 验证 净利润 ≈ 利润总额 - 所得税费用（利润表最核心勾稽）
    for _i, row in income_statement.iterrows():
        year = _year(row["报告日"])
        total_profit = _safe(row.get("利润总额"))
        tax = _safe(row.get("所得税费用"))
        net_income = _safe(row.get("净利润"))

        if total_profit == 0:
            details.append(f"[{year}] 规则2跳过：利润总额为空")
            continue

        expected_net = total_profit - tax
        diff = abs(expected_net - net_income)
        threshold = _soft_threshold(max(abs(total_profit), 1.0))

        if diff > threshold:
            msg = (
                f"[{year}] 利润表勾稽偏差（软等式）："
                f"利润总额-所得税={expected_net:,.0f}，净利润={net_income:,.0f}，"
                f"差异={diff:,.0f}（阈值={threshold:,.0f}）"
            )
            warnings.append(msg)
            details.append(msg)
        else:
            details.append(f"[{year}] 利润表勾稽通过：差异={diff:,.0f}（阈值={threshold:,.0f}）")

    # ── 规则3：现金流量表内部勾稽（软等式）──
    for _i, row in cash_flow.iterrows():
        year = _year(row["报告日"])
        ocf = _safe(row.get("经营活动产生的现金流量净额"))
        icf = _safe(row.get("投资活动产生的现金流量净额"))
        fcf = _safe(row.get("筹资活动产生的现金流量净额"))
        net_change = _safe(row.get("现金及现金等价物净增加额"))

        expected_change = ocf + icf + fcf
        diff = abs(expected_change - net_change)
        threshold = _soft_threshold(max(abs(ocf), abs(icf), abs(fcf), 1.0))

        if diff > threshold:
            msg = (
                f"[{year}] 现金流量表勾稽偏差（软等式）："
                f"经营+投资+筹资={expected_change:,.0f}，净变动={net_change:,.0f}，"
                f"差异={diff:,.0f}（阈值={threshold:,.0f}）"
            )
            warnings.append(msg)
            details.append(msg)
        else:
            details.append(
                f"[{year}] 现金流量表勾稽通过：差异={diff:,.0f}（阈值={threshold:,.0f}）"
            )

    # ── 规则4：留存收益勾稽（软等式）──
    bs_dict = {str(r["报告日"])[:4]: r for _, r in balance_sheet.iterrows()}
    inc_dict = {str(r["报告日"])[:4]: r for _, r in income_statement.iterrows()}
    cf_dict = {str(r["报告日"])[:4]: r for _, r in cash_flow.iterrows()}

    sorted_years = sorted(bs_dict.keys(), reverse=True)
    for idx, year in enumerate(sorted_years):
        row_bs = bs_dict[year]
        retained = _safe(row_bs.get("未分配利润"))
        if retained == 0:
            # 尝试其他可能的列名
            retained = _safe(row_bs.get("未分配利润(或亏损)"))
        if retained == 0:
            details.append(f"[{year}] 规则4跳过：未分配利润列不存在")
            continue

        # 期初 = 上一年期末（跳过最早年份，无历史数据）
        prev_year = sorted_years[idx + 1] if idx + 1 < len(sorted_years) else None
        if prev_year is None:
            details.append(f"[{year}] 规则4跳过：无上一年期初数据")
            continue
        prev_retained = _safe(bs_dict.get(prev_year, {}).get("未分配利润"))

        net_income = _safe(inc_dict.get(year, {}).get("净利润"))
        dividend = _safe(cf_dict.get(year, {}).get("分配股利、利润或偿付利息所支付的现金"))

        expected_retained = prev_retained + net_income - dividend
        diff = abs(expected_retained - retained)
        threshold = _soft_threshold(max(abs(retained), abs(net_income), 1.0))

        if diff > threshold:
            msg = (
                f"[{year}] 留存收益勾稽偏差（软等式）："
                f"期初+净利润-分红={expected_retained:,.0f}，期末={retained:,.0f}，"
                f"差异={diff:,.0f}（阈值={threshold:,.0f}）"
            )
            warnings.append(msg)
            details.append(msg)
        else:
            details.append(f"[{year}] 留存收益勾稽通过：差异={diff:,.0f}（阈值={threshold:,.0f}）")

    return {
        "result": result,
        "warnings": warnings,
        "details": details,
    }
