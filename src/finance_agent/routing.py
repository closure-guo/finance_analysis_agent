"""条件路由函数"""


def after_check_cache(state: dict) -> str:
    result = state.get("cache_result", "MISS")
    if result == "HIT":
        return "compute_metrics"
    return "fetch_data"


def route_to_agent(state: dict) -> list[str]:
    analysis_type = state.get("analysis_type", "financial")
    if analysis_type == "comprehensive":
        return ["fa_analyze", "ia_analyze"]
    if analysis_type == "investment":
        return ["ia_analyze"]
    return ["fa_analyze"]


def after_agent(state: dict) -> str:
    if state.get("analysis_type") == "comprehensive":
        return "merge"
    return "generate_file"
