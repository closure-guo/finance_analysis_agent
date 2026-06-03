"""条件路由函数"""

from langgraph.types import Send


def after_check_cache(state: dict) -> str:
    result = state.get("cache_result", "MISS")
    if result == "HIT":
        return "validate_financials"
    return "fetch_data"


def route_to_agent(state: dict) -> list[Send]:
    analysis_type = state.get("analysis_type", "financial")
    if analysis_type == "comprehensive":
        return [Send("fa_analyze", state), Send("ia_analyze", state)]
    if analysis_type == "investment":
        return [Send("ia_analyze", state)]
    return [Send("fa_analyze", state)]


def after_validate(state: dict) -> str:
    """勾稽校验后路由：FAIL → END，PASS → compute_metrics。"""
    if state.get("validation_result") == "FAIL":
        return "__end__"
    return "compute_metrics"


def after_agent(state: dict) -> str:
    if state.get("analysis_type") == "comprehensive":
        return "merge"
    return "generate_file"
