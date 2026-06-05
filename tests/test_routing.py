"""TDD tests for routing.py — 条件路由函数。"""

from finance_agent.routing import after_agent, after_check_cache, after_validate, route_to_agent


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
