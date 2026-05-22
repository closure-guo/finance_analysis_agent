"""TDD tests for metrics/relative.py — PE/PB 相对估值。

相对估值 = 目标公司 vs 同业均值比较：
- PE < 行业均值 → 低估（green）
- PE 接近均值（±15%）→ 合理（yellow）
- PE > 行业均值×1.15 → 高估（red）

输入：
- target_metrics: {PE: float, PB: float}
- peer_metrics: [{name, PE, PB}, ...]

输出：
- {PE: {target, peer_avg, peer_min, peer_max, conclusion}, PB: ...}
"""

from math import isclose

import pytest

from finance_agent.metrics.relative import calc_relative_valuation


class TestRelativeValuation:
    @pytest.fixture
    def sample_data(self):
        return {
            "target": {"PE": 25.0, "PB": 3.5},
            "peers": [
                {"name": "Peer A", "PE": 30.0, "PB": 4.0},
                {"name": "Peer B", "PE": 28.0, "PB": 3.8},
                {"name": "Peer C", "PE": 22.0, "PB": 3.0},
                {"name": "Peer D", "PE": 26.0, "PB": 3.3},
                {"name": "Peer E", "PE": 24.0, "PB": 3.2},
            ],
        }

    def test_returns_pe_and_pb(self, sample_data):
        result = calc_relative_valuation(
            sample_data["target"], sample_data["peers"]
        )
        assert "PE" in result
        assert "PB" in result

    def test_pe_peer_avg(self, sample_data):
        result = calc_relative_valuation(
            sample_data["target"], sample_data["peers"]
        )
        # (30+28+22+26+24)/5 = 26.0
        assert isclose(result["PE"]["peer_avg"], 26.0, rel_tol=1e-2)

    def test_pe_fair_within_range(self, sample_data):
        result = calc_relative_valuation(
            sample_data["target"], sample_data["peers"]
        )
        # PE=25, avg=26 → 25/26=0.96 → 在 ±15% 内 → fair
        assert result["PE"]["conclusion"] == "fair"

    def test_pe_undervalued(self, sample_data):
        data = {
            "target": {"PE": 18.0, "PB": 2.0},
            "peers": sample_data["peers"],
        }
        result = calc_relative_valuation(data["target"], data["peers"])
        # PE=18, avg=26 → 18/26=0.69 < 0.85 → undervalued
        assert result["PE"]["conclusion"] == "undervalued"

    def test_pe_overvalued(self, sample_data):
        data = {
            "target": {"PE": 35.0, "PB": 5.0},
            "peers": sample_data["peers"],
        }
        result = calc_relative_valuation(data["target"], data["peers"])
        # PE=35, avg=26 → 35/26=1.35 → overvalued
        assert result["PE"]["conclusion"] == "overvalued"

    def test_pb_fair(self, sample_data):
        result = calc_relative_valuation(
            sample_data["target"], sample_data["peers"]
        )
        # PB=3.5, avg=(4+3.8+3+3.3+3.2)/5=3.46 → 3.5/3.46=1.01 → fair
        assert result["PB"]["conclusion"] == "fair"

    def test_no_peers(self):
        result = calc_relative_valuation({"PE": 25.0, "PB": 3.5}, [])
        assert result["PE"]["conclusion"] == "N/A"
        assert result["PB"]["conclusion"] == "N/A"

    def test_peer_min_max(self, sample_data):
        result = calc_relative_valuation(
            sample_data["target"], sample_data["peers"]
        )
        assert isclose(result["PE"]["peer_min"], 22.0)
        assert isclose(result["PE"]["peer_max"], 30.0)

    def test_none_values(self):
        result = calc_relative_valuation(
            {"PE": None, "PB": 3.0},
            [{"name": "A", "PE": 20.0, "PB": 2.5}],
        )
        assert result["PE"]["conclusion"] == "N/A"
