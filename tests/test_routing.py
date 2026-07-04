"""TDD tests for routing.py — 条件路由函数。"""

from finance_agent.routing import (
    after_agent,
    after_check_cache,
    after_citation,
    after_fund_manager,
    after_validate,
    route_to_agent,
)


class TestAfterCheckCache:
    def test_hit_returns_validate(self):
        assert after_check_cache({"cache_result": "HIT"}) == "validate_financials"

    def test_miss_returns_fetch(self):
        assert after_check_cache({"cache_result": "MISS"}) == "fetch_data"

    def test_missing_key_defaults_to_fetch(self):
        assert after_check_cache({}) == "fetch_data"


class TestRouteToAgent:
    def test_financial_routes_to_fa(self):
        result = route_to_agent({"analysis_type": "financial"})
        assert len(result) == 1
        assert result[0].node == "fa_analyze"

    def test_investment_routes_to_ia(self):
        result = route_to_agent({"analysis_type": "investment"})
        assert len(result) == 1
        assert result[0].node == "ia_analyze"

    def test_comprehensive_routes_to_both(self):
        result = route_to_agent({"analysis_type": "comprehensive"})
        assert len(result) == 2
        nodes = {r.node for r in result}
        assert nodes == {"fa_analyze", "ia_analyze"}

    def test_missing_key_defaults_to_financial(self):
        result = route_to_agent({})
        assert len(result) == 1
        assert result[0].node == "fa_analyze"


class TestAfterValidate:
    def test_fail_returns_end(self):
        assert after_validate({"validation_result": "FAIL"}) == "__end__"

    def test_pass_returns_compute(self):
        assert after_validate({"validation_result": "PASS"}) == "compute_metrics"

    def test_missing_key_returns_compute(self):
        assert after_validate({}) == "compute_metrics"


class TestAfterAgent:
    def test_comprehensive_returns_merge(self):
        assert after_agent({"analysis_type": "comprehensive"}) == "merge"

    def test_financial_returns_generate(self):
        assert after_agent({"analysis_type": "financial"}) == "generate_file"

    def test_investment_returns_generate(self):
        assert after_agent({"analysis_type": "investment"}) == "generate_file"

    def test_missing_key_returns_generate(self):
        assert after_agent({}) == "generate_file"


class TestAfterFundManager:
    """Layer V Fund Manager 路由：批准/拒绝/退回。"""

    def test_approve_returns_generate_report(self):
        state = {"fund_manager_decision": "approve"}
        assert after_fund_manager(state) == "generate_report"

    def test_reject_returns_generate_report(self):
        state = {"fund_manager_decision": "reject"}
        assert after_fund_manager(state) == "generate_report"

    def test_return_with_zero_count_returns_trader(self):
        state = {"fund_manager_decision": "return", "return_count": 0}
        assert after_fund_manager(state) == "trader"

    def test_return_with_max_count_returns_generate_report(self):
        """退回次数已达上限（1 次），强制进入报告生成。"""
        state = {"fund_manager_decision": "return", "return_count": 1}
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
