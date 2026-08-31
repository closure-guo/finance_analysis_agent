"""TDD tests for routing.py — 条件路由函数。"""

from finance_agent.routing import (
    after_check_cache,
    after_citation,
    after_fund_manager,
    after_validate,
)


class TestAfterCheckCache:
    def test_hit_returns_validate(self):
        assert after_check_cache({"cache_result": "HIT"}) == "validate_financials"

    def test_miss_returns_fetch(self):
        assert after_check_cache({"cache_result": "MISS"}) == "fetch_data"

    def test_missing_key_defaults_to_fetch(self):
        assert after_check_cache({}) == "fetch_data"


class TestAfterValidate:
    def test_fail_returns_end(self):
        assert after_validate({"validation_result": "FAIL"}) == "__end__"

    def test_pass_returns_compute(self):
        assert after_validate({"validation_result": "PASS"}) == "compute_metrics"

    def test_missing_key_returns_compute(self):
        assert after_validate({}) == "compute_metrics"


class TestAfterFundManager:
    """Layer V Fund Manager 路由：批准/拒绝/退回。"""

    def test_approve_returns_generate_report(self):
        state = {"fund_manager_decision": "approve"}
        assert after_fund_manager(state) == "generate_report"

    def test_reject_returns_generate_report(self):
        """reject 仍进入报告生成 —— 符合 ADR-0011 Layer V「Reject → 报告标注未通过审批」。

        本用例把「reject 走 generate_report」固化为基线，但这**不代表** reject
        语义等价于 approve：两者的区分由报告中的中文标注承担
        （report.py 的 _FUND_MANAGER_ANNOTATIONS，reject 标注为「未通过审批」）。
        """
        state = {"fund_manager_decision": "reject"}
        assert after_fund_manager(state) == "generate_report"

    def test_return_with_zero_count_returns_trader(self):
        state = {"fund_manager_decision": "return", "return_count": 0}
        assert after_fund_manager(state) == "trader"

    def test_return_with_one_count_returns_trader(self):
        """已退回 1 次（节点刚递增），仍允许退回 Trader 重新评估。"""
        state = {"fund_manager_decision": "return", "return_count": 1}
        assert after_fund_manager(state) == "trader"

    def test_return_with_max_count_returns_generate_report(self):
        """退回次数已达上限（2 次），强制进入报告生成。"""
        state = {"fund_manager_decision": "return", "return_count": 2}
        assert after_fund_manager(state) == "generate_report"


class TestAfterCitation:
    """引用校验路由：PASS → 渲染，FAIL → 重试（最多 3 次）。"""

    def test_pass_returns_render(self):
        state = {"citation_pass": True, "iteration_count": 0}
        assert after_citation(state) == "render"

    def test_fail_below_max_returns_retry(self):
        state = {"citation_pass": False, "iteration_count": 1}
        assert after_citation(state) == "retry"

    def test_fail_at_max_returns_render(self):
        """重试次数达上限（3 次），强制渲染。"""
        state = {"citation_pass": False, "iteration_count": 3}
        assert after_citation(state) == "render"


class TestAfterCitationDeescalation:
    """citation-retry-policy delta：失败率无显著改善时提前放行渲染。

    线上事故（601700 深研）：三轮失败率 35%→38%→31%，重试零收益，
    每轮全量重跑 4 分析师白烧 ~40 分钟。
    """

    def test_fail_rate_stagnant_returns_render(self):
        """最新失败率 ≥ 上一轮的 80%（无显著改善）时不再重试。"""
        state = {
            "citation_pass": False,
            "iteration_count": 2,
            "citation_fail_rates": [0.35, 0.31],
        }
        assert after_citation(state) == "render"

    def test_fail_rate_improved_returns_retry(self):
        """失败率显著改善（< 上一轮 80%）时按上限继续重试。"""
        state = {
            "citation_pass": False,
            "iteration_count": 2,
            "citation_fail_rates": [0.60, 0.20],
        }
        assert after_citation(state) == "retry"

    def test_single_round_failure_still_retries(self):
        """首轮失败（无历史失败率）不降级，按既有行为重试。"""
        state = {
            "citation_pass": False,
            "iteration_count": 1,
            "citation_fail_rates": [0.9],
        }
        assert after_citation(state) == "retry"

    def test_cap_still_enforced_without_rates(self):
        """无失败率历史时上限语义不变（< 3 重试，>= 3 放行）。"""
        assert after_citation({"citation_pass": False, "iteration_count": 2}) == "retry"
        assert after_citation({"citation_pass": False, "iteration_count": 3}) == "render"


class TestAfterCitationMinorFail:
    """skip-citation-retry-on-minor-failures：FAIL≤1 且失败率≤5% 免重试。"""

    def test_minor_fail_returns_render(self):
        state = {
            "citation_pass": False,
            "citation_minor_fail": True,
            "iteration_count": 1,
            "citation_fail_rates": [0.022],
        }
        assert after_citation(state) == "render"

    def test_non_minor_fail_still_retries(self):
        state = {
            "citation_pass": False,
            "citation_minor_fail": False,
            "iteration_count": 1,
            "citation_fail_rates": [0.542],
        }
        assert after_citation(state) == "retry"

    def test_cap_still_enforced_with_minor_flag(self):
        """轮数上限优先：即使轻微失败标记为假但已达 3 轮仍渲染。"""
        state = {"citation_pass": False, "citation_minor_fail": False, "iteration_count": 3}
        assert after_citation(state) == "render"
