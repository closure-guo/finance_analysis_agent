"""compute.py 单元测试 — 验证编排层正确写入 State 字段。"""

import pandas as pd
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


@pytest.fixture
def kline_state(sample_state):
    """带 K 线数据的 state，用于技术指标和风控指标计算。"""
    sample_state["kline"] = pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-02", periods=30, freq="B"),
            "开盘": [float(i) for i in range(10, 40)],
            "收盘": [float(i) for i in range(11, 41)],
            "最高": [float(i) for i in range(11, 41)],
            "最低": [float(i) for i in range(10, 40)],
            "成交量": [1000 + i * 100 for i in range(30)],
        }
    )
    return sample_state


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

    def test_technical_indicators_when_kline_present(self, kline_state):
        """有 K 线数据时计算技术指标。"""
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(kline_state)
        assert "technical_indicators" in result
        assert "MA" in result["technical_indicators"]
        assert "MACD" in result["technical_indicators"]

    def test_risk_metrics_when_kline_present(self, kline_state):
        """有 K 线数据时计算风控指标。"""
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(kline_state)
        assert "risk_metrics" in result
        assert "max_drawdown" in result["risk_metrics"]
        assert "volatility" in result["risk_metrics"]

    def test_no_technical_when_kline_absent(self, sample_state):
        """无 K 线数据时不产出技术指标。"""
        from finance_agent.nodes.compute import compute_metrics

        result = compute_metrics(sample_state)
        assert "technical_indicators" not in result
        assert "risk_metrics" not in result
