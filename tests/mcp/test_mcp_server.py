"""TDD tests for MCP server: run_prep pipeline + 5 tools.

run_prep chains check_cache → fetch_data → validate → compute_metrics.
Each MCP tool calls run_prep and extracts/format relevant data.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from finance_agent.mcp_server import (
    create_server,
    get_dupont_analysis,
    get_financial_health,
    get_financial_statements,
    get_peer_comparison,
    get_valuation,
    run_prep,
)


def _make_full_state(stock_code="600519"):
    """Build a minimal state dict that looks like PREP pipeline output."""
    return {
        "stock_code": stock_code,
        "cache_result": "HIT",
        "validation_result": "PASS",
        "validation_warnings": [],
        "balance_sheet": pd.DataFrame({"报告日": ["20241231"], "资产总计": [1000.0]}),
        "income_statement": pd.DataFrame({"报告日": ["20241231"], "营业收入": [100.0]}),
        "cash_flow_statement": pd.DataFrame({"报告日": ["20241231"]}),
        "industry_info": {"industry": "白酒"},
        "stock_quote": {"PE": 30.0, "PB": 8.0},
        "financial_indicators": None,
        "solvency_metrics": {"资产负债率": {"2024": 40.0}},
        "profitability_metrics": {"ROE": {"2024": 18.0}},
        "efficiency_metrics": {"总资产周转率": {"2024": 1.05}},
        "cashflow_metrics": {"FCF": {"2024": 170.0}},
        "traffic_lights": {
            "solvency": {"资产负债率": {"2024": {"final": "yellow"}}},
        },
        "health_score": {"total": 85, "level": "健康"},
        "dupont_tree": {"L1": {"ROE": 0.18}},
        "relative_valuation": {"PE": {"target": 30.0, "industry_avg": 25.0}},
        "garp_result": {"pass": True},
        "peer_financials": pd.DataFrame({"name": ["五粮液"], "PE": [25.0]}),
        "peer_comparison": {"available": True},
    }


# ── run_prep ──


class TestRunPrepMissPath:
    """MISS: check_cache → fetch_data → validate → compute_metrics."""

    @patch("finance_agent.mcp_server.compute_metrics")
    @patch("finance_agent.mcp_server.validate_node")
    @patch("finance_agent.mcp_server.fetch_data")
    @patch("finance_agent.mcp_server.check_cache")
    def test_miss_calls_full_chain(self, mock_cache, mock_fetch, mock_validate, mock_compute):
        mock_cache.return_value = {"cache_result": "MISS"}
        mock_fetch.return_value = {"balance_sheet": pd.DataFrame()}
        mock_validate.return_value = {"validation_result": "PASS", "validation_warnings": []}
        mock_compute.return_value = {"solvency_metrics": {}}

        result = run_prep("600519")

        mock_cache.assert_called_once()
        mock_fetch.assert_called_once()
        mock_validate.assert_called_once()
        mock_compute.assert_called_once()
        assert result["solvency_metrics"] == {}


class TestRunPrepHitPath:
    """HIT: check_cache → validate → compute_metrics (skip fetch)."""

    @patch("finance_agent.mcp_server.compute_metrics")
    @patch("finance_agent.mcp_server.validate_node")
    @patch("finance_agent.mcp_server.fetch_data")
    @patch("finance_agent.mcp_server.check_cache")
    def test_hit_skips_fetch(self, mock_cache, mock_fetch, mock_validate, mock_compute):
        mock_cache.return_value = {"cache_result": "HIT", "balance_sheet": pd.DataFrame()}
        mock_validate.return_value = {"validation_result": "PASS", "validation_warnings": []}
        mock_compute.return_value = {"solvency_metrics": {}}

        result = run_prep("600519")

        mock_fetch.assert_not_called()
        assert result["solvency_metrics"] == {}


class TestRunPrepValidationFail:
    """校验失败时抛异常。"""

    @patch("finance_agent.mcp_server.compute_metrics")
    @patch("finance_agent.mcp_server.validate_node")
    @patch("finance_agent.mcp_server.check_cache")
    def test_raises_on_validation_fail(self, mock_cache, mock_validate, mock_compute):
        mock_cache.return_value = {"cache_result": "HIT", "balance_sheet": pd.DataFrame()}
        mock_validate.return_value = {
            "validation_result": "FAIL",
            "validation_warnings": ["试算不平衡"],
        }

        with pytest.raises(ValueError, match="试算不平衡"):
            run_prep("600519")

        mock_compute.assert_not_called()


# ── get_financial_health ──


class TestGetFinancialHealth:
    """get_financial_health 返回四维度指标 + 红黄绿灯 + 评分，带阈值上下文。"""

    @patch("finance_agent.mcp_server.run_prep")
    def test_returns_four_dimensions_with_lights(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_financial_health("600519")

        assert "solvency" in result["metrics"]
        assert "profitability" in result["metrics"]
        assert "efficiency" in result["metrics"]
        assert "cashflow" in result["metrics"]

    @patch("finance_agent.mcp_server.run_prep")
    def test_includes_traffic_lights(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_financial_health("600519")

        solv = result["metrics"]["solvency"]
        assert "资产负债率" in solv
        entry = solv["资产负债率"]
        assert "value" in entry
        assert "light" in entry
        assert "thresholds" in entry

    @patch("finance_agent.mcp_server.run_prep")
    def test_includes_health_score(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_financial_health("600519")

        assert result["health_score"]["total"] == 85
        assert result["health_score"]["level"] == "健康"


# ── get_valuation ──


class TestGetValuation:
    """get_valuation 返回 PE/PB 同业对比 + GARP 结果。"""

    @patch("finance_agent.mcp_server.run_prep")
    def test_returns_relative_valuation(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_valuation("600519")

        assert result["relative_valuation"]["PE"]["target"] == 30.0
        assert result["relative_valuation"]["PE"]["industry_avg"] == 25.0

    @patch("finance_agent.mcp_server.run_prep")
    def test_returns_garp(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_valuation("600519")

        assert result["garp_result"]["pass"] is True


# ── get_dupont_analysis ──


class TestGetDupontAnalysis:
    """get_dupont_analysis 返回 3 层杜邦拆解。"""

    @patch("finance_agent.mcp_server.run_prep")
    def test_returns_dupont_tree(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_dupont_analysis("600519")

        assert result["dupont_tree"]["L1"]["ROE"] == 0.18


# ── get_peer_comparison ──


class TestGetPeerComparison:
    """get_peer_comparison 返回同业对比数据。"""

    @patch("finance_agent.mcp_server.run_prep")
    def test_returns_peer_data(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_peer_comparison("600519")

        assert result["peer_financials"] is not None
        assert result["peer_comparison"]["available"] is True


# ── get_financial_statements ──


class TestGetFinancialStatements:
    """get_financial_statements 返回原始三大报表。"""

    @patch("finance_agent.mcp_server.run_prep")
    def test_returns_three_statements(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_financial_statements("600519")

        assert "balance_sheet" in result
        assert "income_statement" in result
        assert "cash_flow_statement" in result

    @patch("finance_agent.mcp_server.run_prep")
    def test_preserves_raw_data(self, mock_prep):
        mock_prep.return_value = _make_full_state()

        result = get_financial_statements("600519")

        assert result["balance_sheet"]["资产总计"].tolist() == [1000.0]
        assert result["income_statement"]["营业收入"].tolist() == [100.0]


# ── MCP server registration ──


class TestMCPServerRegistration:
    """create_server 注册全部 5 个 tool。"""

    def test_server_has_five_tools(self):
        import asyncio

        server = create_server()
        tools = asyncio.run(server.list_tools())
        tool_names = {t.name for t in tools}
        expected = {
            "get_financial_health",
            "get_valuation",
            "get_dupont_analysis",
            "get_peer_comparison",
            "get_financial_statements",
        }
        assert tool_names == expected
