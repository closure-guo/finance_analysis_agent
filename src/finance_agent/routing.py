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


# citation-retry-policy delta：重试降级的"无显著改善"阈值。线上事故
# （601700 深研）三轮失败率 35%→38%→31%，重试零收益却每轮全量重跑
# 4 分析师白烧 ~40 分钟——失败是系统性的（claim field_ref 与数据形态
# 不匹配），非随机噪声，降级判定按最新失败率 ≥ 上一轮 × 80% 触发。
_CITATION_STAGNATION_FACTOR = 0.8


def citation_retry_stagnated(fail_rates: list[float]) -> bool:
    """判定失败率序列是否停滞（重试无收益）：需至少两轮且最新一轮
    失败率不低于上一轮的 80%；上一轮失败率为 0 时不判停滞（比值无意义）。"""
    if len(fail_rates) < 2:
        return False
    prev, curr = fail_rates[-2], fail_rates[-1]
    return bool(prev > 0 and curr >= prev * _CITATION_STAGNATION_FACTOR)


def after_citation(state: dict) -> str:
    """引用校验路由：PASS → 渲染，轻微失败（≤1 条且 ≤5%）→ 渲染，FAIL → 重试（最多 3 次）。"""
    if state.get("citation_pass", False) or state.get("citation_minor_fail", False):
        return "render"
    if state.get("iteration_count", 0) < 3:
        # citation-retry-policy delta：重试无收益（失败率无显著改善）时
        # 提前放行渲染；轮数上限 3 不因降级放宽（stagnated 只会提前，不会延后）。
        if citation_retry_stagnated(state.get("citation_fail_rates") or []):
            return "render"
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
