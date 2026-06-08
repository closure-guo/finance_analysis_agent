"""MCP Server: expose financial analysis as MCP tools for Claude Desktop.

ADR 0008: 5 tools returning structured metrics (no LLM text).
Reuses existing PREP node functions via run_prep().
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastmcp import FastMCP

from finance_agent.metrics.traffic_light import ABSOLUTE_THRESHOLDS
from finance_agent.nodes.cache import check_cache
from finance_agent.nodes.compute import compute_metrics
from finance_agent.nodes.fetch import fetch_data
from finance_agent.nodes.validate import validate_node

_DIMENSION_KEYS = {
    "solvency": "solvency_metrics",
    "profitability": "profitability_metrics",
    "efficiency": "efficiency_metrics",
    "cashflow": "cashflow_metrics",
}


def run_prep(stock_code: str, peer_codes: list[str] | None = None) -> dict:
    state: dict = {"stock_code": stock_code, "peer_codes": peer_codes}

    state.update(check_cache(state))

    if state["cache_result"] == "MISS":
        state.update(fetch_data(state))

    state.update(validate_node(state))
    if state["validation_result"] == "FAIL":
        raise ValueError(str(state.get("validation_warnings", [])))

    state.update(compute_metrics(state))
    return state


def _enrich_metrics(
    dim_metrics: dict[str, dict],
    lights: dict[str, dict[str, dict]],
    dim_name: str,
) -> dict[str, dict]:
    """合并指标值 + 红黄绿灯 + 阈值上下文。"""
    dim_lights = lights.get(dim_name, {})
    result: dict[str, dict] = {}
    for metric_name, year_values in dim_metrics.items():
        entry: dict = {"value": year_values, "light": dim_lights.get(metric_name, {})}
        thresh = ABSOLUTE_THRESHOLDS.get(metric_name)
        if thresh:
            green, yellow, higher_is_better = thresh
            entry["thresholds"] = {
                "green": green,
                "yellow": yellow,
                "higher_is_better": higher_is_better,
            }
        else:
            entry["thresholds"] = None
        result[metric_name] = entry
    return result


def get_financial_health(stock_code: str) -> dict:
    state = run_prep(stock_code)
    traffic_lights = state.get("traffic_lights", {})
    metrics: dict[str, dict] = {}
    for dim_name, state_key in _DIMENSION_KEYS.items():
        dim_data = state.get(state_key, {})
        if dim_data:
            metrics[dim_name] = _enrich_metrics(dim_data, traffic_lights, dim_name)
    return {"metrics": metrics, "health_score": state.get("health_score")}


def get_valuation(stock_code: str) -> dict:
    state = run_prep(stock_code)
    return {
        "relative_valuation": state.get("relative_valuation"),
        "garp_result": state.get("garp_result"),
    }


def get_dupont_analysis(stock_code: str) -> dict:
    state = run_prep(stock_code)
    return {"dupont_tree": state.get("dupont_tree")}


def get_peer_comparison(stock_code: str) -> dict:
    state = run_prep(stock_code)
    return {
        "peer_financials": state.get("peer_financials"),
        "peer_comparison": state.get("peer_comparison"),
    }


def get_financial_statements(stock_code: str) -> dict:
    state = run_prep(stock_code)
    return {
        "balance_sheet": state.get("balance_sheet"),
        "income_statement": state.get("income_statement"),
        "cash_flow_statement": state.get("cash_flow_statement"),
    }


def _serialize(val: Any) -> Any:
    """递归转换 DataFrame 为 JSON 可序列化结构。"""
    if isinstance(val, pd.DataFrame):
        return val.to_dict(orient="records")
    if isinstance(val, dict):
        return {k: _serialize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize(v) for v in val]
    return val


def create_server() -> FastMCP:
    """创建 MCP Server，注册全部 5 个 tool（stdio）。"""
    import finance_agent.mcp_server as _self

    mcp = FastMCP("finance-agent")

    @mcp.tool
    def get_financial_health(stock_code: str) -> dict:
        return _serialize(_self.get_financial_health(stock_code))

    @mcp.tool
    def get_valuation(stock_code: str) -> dict:
        return _serialize(_self.get_valuation(stock_code))

    @mcp.tool
    def get_dupont_analysis(stock_code: str) -> dict:
        return _serialize(_self.get_dupont_analysis(stock_code))

    @mcp.tool
    def get_peer_comparison(stock_code: str) -> dict:
        return _serialize(_self.get_peer_comparison(stock_code))

    @mcp.tool
    def get_financial_statements(stock_code: str) -> dict:
        return _serialize(_self.get_financial_statements(stock_code))

    return mcp


def main():
    create_server().run()


if __name__ == "__main__":
    main()
