"""compute.py 单元测试 — 验证编排层正确写入 State 字段。"""

import pytest


@pytest.fixture
def sample_state(balance_sheet, income_statement, cash_flow, indicators):
    return {
        "balance_sheet": balance_sheet,
        "income_statement": income_statement,
        "cash_flow_statement": cash_flow,
        "financial_indicators": indicators,
        "stock_quote": {},
        "industry_info": {},
        "peer_financials": None,
    }


class TestComputeMetrics:
    def test_returns_all_metric_keys(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        expected_keys = [
            "solvency_metrics",
            "profitability_metrics",
            "efficiency_metrics",
            "cashflow_metrics",
            "dupont_tree",
            "traffic_lights",
            "growth_rates",
            "anomalies",
            "garp_result",
        ]
        for key in expected_keys:
            assert key in result, f"missing key: {key}"

    def test_solvency_has_5_metrics(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        solv = result["solvency_metrics"]
        assert len(solv) == 5
        assert "资产负债率" in solv

    def test_profitability_has_5_metrics(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        prof = result["profitability_metrics"]
        assert len(prof) == 5
        assert "ROE" in prof

    def test_traffic_lights_structure(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        tl = result["traffic_lights"]
        assert "solvency" in tl
        assert "profitability" in tl

    def test_health_score_exists(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        assert "health_score" in result
        score = result["health_score"]
        assert "total" in score
        assert "rating" in score
        assert score["total"] >= 0

    def test_growth_rates_not_empty(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        gr = result["growth_rates"]
        assert len(gr) > 0

    def test_anomalies_is_list(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        assert isinstance(result["anomalies"], list)

    def test_dupont_tree_has_levels(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        dupont = result["dupont_tree"]
        assert "L1" in dupont

    def test_garp_result_exists(self, sample_state):
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        assert "garp_result" in result
        assert "pass" in result["garp_result"]
