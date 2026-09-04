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
    """引用校验路由（harden-citation-semantic-coverage 按桶分流）：

    PASS / 轻微失败 → 渲染；仅值级 FAIL（value_mismatch）触发定向重试
    （citation_retry_targets 非空）；格式类 FAIL（术语/期次/内部不一致、
    路径不可解析）与 UNVERIFIABLE 直判放行不重试（实测三轮停滞
    35%→38%→31%，重试零收益却每轮全量重跑 4 分析师白烧 ~40 分钟——
    失败是系统性的（claim field_ref 与数据形态不匹配），非随机噪声，降级
    判定按最新失败率 ≥ 上一轮 × 80% 触发）；轮次上限与停滞降级语义不变。
    """
    # D6：coverage 缺口（值级全过但正文数字未认领）→ 定向打回补 claim，共享迭代上限
    if (
        state.get("citation_coverage_gap")
        and state.get("citation_retry_targets")
        and state.get("iteration_count", 0) < 3
    ):
        return "retry"
    if state.get("citation_pass", False) or state.get("citation_minor_fail", False):
        return "render"
    if not state.get("citation_retry_targets"):
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
    """Layer I 派发：首轮 4 分析师并行；引用校验重试轮只 Send 值级 FAIL 的目标
    分析师（harden-citation-semantic-coverage 定向重试），其余分析师结果复用
    （analyst_reports merge_dicts 保留旧值，重跑覆盖目标键）。"""
    all_sends = {
        "technical": Send("technical_analyst", state),
        "macro": Send("macro_analyst", state),
        "fundamental": Send("fundamental_analyst", state),
        "sentiment": Send("sentiment_analyst", state),
    }
    targets = state.get("citation_retry_targets") or []
    if targets:
        return [all_sends[t] for t in targets if t in all_sends]
    return list(all_sends.values())


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


def after_validate_trade_prices(state: dict) -> str:
    """toolize-price-levels：价位 sanity 校验路由。pass/corrected 前行，fail 打回 trader。"""
    check = state.get("price_check") or {}
    if check.get("result") == "fail":
        return "trader"
    return "risk_r1_entry"
