"""validate_financials: 勾稽校验节点 — 三大报表数据质量验证。

在 compute_metrics 之前执行，硬等式失败时短路终止。
"""

from __future__ import annotations

from finance_agent.metrics.validate import validate_financials


def validate_node(state: dict) -> dict:
    """执行勾稽校验，结果写入 state。

    Returns
    -------
    dict
        {"validation_result": "PASS" | "FAIL", "validation_warnings": list[str]}
    """
    bs = state.get("balance_sheet")
    inc = state.get("income_statement")
    cf = state.get("cash_flow_statement")

    if bs is None or inc is None or cf is None:
        return {
            "validation_result": "FAIL",
            "validation_warnings": ["勾稽校验跳过：三大报表数据缺失"],
        }

    result = validate_financials(bs, inc, cf)
    return {
        "validation_result": result["result"],
        "validation_warnings": result["warnings"],
    }
