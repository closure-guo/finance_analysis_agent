"""条件路由函数"""

from langgraph.types import Send


def after_check_cache(state: dict) -> str:
    result = state.get("cache_result", "MISS")
    if result == "HIT":
        return "validate_financials"
    return "fetch_data"


def after_validate(state: dict) -> str:
    """勾稽校验后路由：FAIL -> END，PASS -> compute_metrics。"""
    if state.get("validation_result") == "FAIL":
        return "__end__"
    return "compute_metrics"


# ── 5 层架构路由函数（ADR-0011）──


def after_fund_manager(state: dict) -> str:
    """Layer V Fund Manager 路由：退回 Trader（最多 1 次）或生成报告。"""
    decision = state.get("fund_manager_decision", "approve")
    if decision == "return" and state.get("return_count", 0) <= 1:
        return "trader"
    return "generate_report"


def after_citation(state: dict) -> str:
    """引用校验路由：PASS → 渲染，FAIL → 重试（最多 3 次）。"""
    if state.get("citation_pass", False):
        return "render"
    if state.get("iteration_count", 0) < 3:
        return "retry"
    return "render"


# ── Send 并行派发函数 ──


def route_to_analysts(state: dict) -> list[Send]:
    """Layer I: 派发到 4 个并行分析师。"""
    return [
        Send("technical_analyst", state),
        Send("macro_analyst", state),
        Send("fundamental_analyst", state),
        Send("sentiment_analyst", state),
    ]


def route_to_debate_r1(state: dict) -> list[Send]:
    """Layer II Round 1: 派发到 Bull/Bear。"""
    return [Send("bull_r1", state), Send("bear_r1", state)]


def route_to_debate_r2(state: dict) -> list[Send]:
    """Layer II Round 2: 派发到 Bull/Bear。"""
    return [Send("bull_r2", state), Send("bear_r2", state)]


def route_to_risk_r1(state: dict) -> list[Send]:
    """Layer IV Round 1: 派发到 3 个风险辩论者。"""
    return [
        Send("aggressive_r1", state),
        Send("conservative_r1", state),
        Send("neutral_r1", state),
    ]


def route_to_risk_r2(state: dict) -> list[Send]:
    """Layer IV Round 2: 派发到 3 个风险辩论者。"""
    return [
        Send("aggressive_r2", state),
        Send("conservative_r2", state),
        Send("neutral_r2", state),
    ]
