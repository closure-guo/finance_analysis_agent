"""TDD tests for metrics/garp.py — GARP 筛选。

GARP = Growth at a Reasonable Price
条件：PE < 行业平均 ∧ 净利润增长率 > 15% ∧ ROE > 15% ∧ 负债率 < 60%
全部满足 → pass, 否则 → fail（附带哪些条件未满足）
"""

import pytest

from finance_agent.metrics.garp import calc_garp


class TestGARP:
    @pytest.fixture
    def passing_data(self):
        return {
            "PE": 20.0,
            "industry_avg_PE": 25.0,
            "net_profit_growth": 0.25,
            "ROE": 0.20,
            "debt_ratio": 0.45,
        }

    def test_all_conditions_met(self, passing_data):
        result = calc_garp(passing_data)
        assert result["pass"] is True
        assert len(result["failures"]) == 0

    def test_pe_too_high(self, passing_data):
        passing_data["PE"] = 30.0  # > industry_avg_PE=25
        result = calc_garp(passing_data)
        assert result["pass"] is False
        assert "PE >= 行业平均" in result["failures"]

    def test_growth_too_low(self, passing_data):
        passing_data["net_profit_growth"] = 0.10  # < 15%
        result = calc_garp(passing_data)
        assert result["pass"] is False
        assert "净利润增长率 <= 15%" in result["failures"]

    def test_roe_too_low(self, passing_data):
        passing_data["ROE"] = 0.10  # < 15%
        result = calc_garp(passing_data)
        assert result["pass"] is False
        assert "ROE <= 15%" in result["failures"]

    def test_debt_too_high(self, passing_data):
        passing_data["debt_ratio"] = 0.65  # > 60%
        result = calc_garp(passing_data)
        assert result["pass"] is False
        assert "负债率 >= 60%" in result["failures"]

    def test_multiple_failures(self, passing_data):
        passing_data["PE"] = 30.0
        passing_data["ROE"] = 0.10
        result = calc_garp(passing_data)
        assert result["pass"] is False
        assert len(result["failures"]) == 2

    def test_none_values(self):
        result = calc_garp(
            {
                "PE": None,
                "industry_avg_PE": 25.0,
                "net_profit_growth": None,
                "ROE": 0.20,
                "debt_ratio": 0.45,
            }
        )
        assert result["pass"] is False
        assert len(result["failures"]) == 2  # PE None and growth None

    def test_boundary_values(self):
        # Exactly at boundaries should pass
        result = calc_garp(
            {
                "PE": 25.0,  # == industry_avg → should NOT pass (need <)
                "industry_avg_PE": 25.0,
                "net_profit_growth": 0.15,  # == 15% → should NOT pass (need >)
                "ROE": 0.15,  # == 15% → should NOT pass (need >)
                "debt_ratio": 0.60,  # == 60% → should NOT pass (need <)
            }
        )
        assert result["pass"] is False
        assert len(result["failures"]) == 4
