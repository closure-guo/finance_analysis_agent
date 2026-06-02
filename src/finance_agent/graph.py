"""LangGraph 主图定义：9 节点（8 实际 + 1 虚拟路由）+ 条件路由"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from finance_agent.nodes.cache import check_cache
from finance_agent.nodes.compute import compute_metrics
from finance_agent.nodes.fa import fa_analyze
from finance_agent.nodes.fetch import fetch_data
from finance_agent.nodes.ia import ia_analyze
from finance_agent.nodes.merge import merge_reports
from finance_agent.nodes.output import generate_file
from finance_agent.nodes.validate import validate_node
from finance_agent.routing import after_agent, after_check_cache, after_validate, route_to_agent
from finance_agent.state import AnalysisState


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AnalysisState)  # pyrefly: ignore[bad-specialization]

    # 数据准备子图节点
    graph.add_node("check_cache", check_cache)
    graph.add_node("fetch_data", fetch_data)
    graph.add_node("validate_financials", validate_node)
    graph.add_node("compute_metrics", compute_metrics)

    # Agent 子图节点
    graph.add_node("fa_analyze", fa_analyze)
    graph.add_node("ia_analyze", ia_analyze)

    # 后处理节点
    graph.add_node("merge", merge_reports)
    graph.add_node("generate_file", generate_file)

    # 边：数据准备
    graph.add_edge(START, "check_cache")
    graph.add_conditional_edges("check_cache", after_check_cache)
    graph.add_edge("fetch_data", "validate_financials")
    graph.add_conditional_edges("validate_financials", after_validate)
    graph.add_edge("compute_metrics", "route")

    # 虚拟路由节点（fan-out 到 Agent 子图）
    def route_node(state: dict) -> dict:
        return state

    graph.add_node("route", route_node)
    graph.add_conditional_edges("route", route_to_agent)

    # Agent → 条件路由（comprehensive → merge，single-agent → generate_file）
    graph.add_conditional_edges("fa_analyze", after_agent)
    graph.add_conditional_edges("ia_analyze", after_agent)
    graph.add_edge("merge", "generate_file")
    graph.add_edge("generate_file", END)

    return graph.compile()
