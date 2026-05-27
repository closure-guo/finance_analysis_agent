"""TDD tests for metrics/traffic_light.py — 双重阈值红黄绿灯 + 健康度评分。

双重阈值评判：
- 绝对值水平：优良🟢 / 关注🟡 / 警告🔴（各指标阈值不同）
- 同比变化率：<20%🟢 / 20-50%🟡 / >50%🔴
- 最终灯色 = max(绝对值灯, 变化率灯)

评分：四维度各 25 分，🟢=满分 🟡=半分 🔴=零分
85-100=健康 | 60-84=关注 | <60=警告

指标分组：
- 偿债(5): 资产负债率, 流动比率, 速动比率, 利息覆盖倍数, 净债务/EBITDA
- 盈利(5): 毛利率, 净利率, ROE, ROA, ROIC
- 运营(4): 存货周转率, 应收账款周转率, 总资产周转率, 应付账款周转率
- 现金流(6): 经营现金流/净利润, FCF, 资本支出/折旧, 现金流覆盖比率, FCF收益率, 留存现金流比率
"""

from math import isclose

import pytest

from finance_agent.metrics.traffic_light import (
    _apply_safety_floor,
    assess_change_rate,
    assess_traffic_lights,
    compute_health_score,
)

# ── 变化率评判 ──


class TestChangeRate:
    def test_stable(self):
        assert assess_change_rate(0.10) == "green"

    def test_moderate(self):
        assert assess_change_rate(0.30) == "yellow"

    def test_volatile(self):
        assert assess_change_rate(0.60) == "red"

    def test_negative_change(self):
        """负变化率取绝对值评判。"""
        assert assess_change_rate(-0.10) == "green"
        assert assess_change_rate(-0.30) == "yellow"
        assert assess_change_rate(-0.60) == "red"

    def test_boundary_20_percent(self):
        assert assess_change_rate(0.20) == "yellow"

    def test_boundary_50_percent(self):
        assert assess_change_rate(0.50) == "yellow"

    def test_just_above_50(self):
        assert assess_change_rate(0.501) == "red"


# ── 红黄绿灯矩阵 ──


class TestTrafficLights:
    @pytest.fixture
    def sample_metrics(self):
        return {
            "solvency": {
                "资产负债率": {"2024": 35.0, "2023": 40.0, "2022": 45.0},
                "流动比率": {"2024": 2.5, "2023": 2.0, "2022": 1.8},
                "速动比率": {"2024": 2.0, "2023": 1.6, "2022": 1.4},
                "利息覆盖倍数": {"2024": 11.0, "2023": 10.0, "2022": 9.0},
                "净债务/EBITDA": {"2024": -0.08, "2023": 0.5, "2022": 1.0},
            },
            "profitability": {
                "毛利率": {"2024": 40.0, "2023": 38.89, "2022": 37.5},
                "净利率": {"2024": 17.0, "2023": 17.0, "2022": 17.0},
                "ROE": {"2024": 28.33, "2023": 27.82, "2022": 28.33},
                "ROA": {"2024": 17.0, "2023": 17.0, "2022": 17.0},
                "ROIC": {"2024": 23.97, "2023": 22.0, "2022": 20.0},
            },
            "efficiency": {
                "存货周转率": {"2024": 6.32, "2023": 6.47, "2022": 6.58},
                "应收账款周转率": {"2024": None, "2023": None, "2022": None},
                "总资产周转率": {"2024": 1.05, "2023": 1.06, "2022": 1.05},
                "应付账款周转率": {"2024": 10.0, "2023": 11.0, "2022": 11.11},
            },
            "cashflow": {
                "经营现金流/净利润": {"2024": 1.47, "2023": 1.44, "2022": 1.47},
                "FCF": {"2024": 170.0, "2023": 150.0, "2022": 140.0},
                "资本支出/折旧": {"2024": 4.0, "2023": 3.5, "2022": 3.0},
                "现金流覆盖比率": {"2024": 1.7, "2023": 1.5, "2022": 1.4},
                "FCF收益率": {"2024": 0.17, "2023": 0.167, "2022": 0.175},
                "留存现金流比率": {"2024": 0.706, "2023": 0.70, "2022": 0.714},
            },
        }

    def test_returns_all_dimensions(self, sample_metrics):
        result = assess_traffic_lights(sample_metrics)
        expected_dims = {"solvency", "profitability", "efficiency", "cashflow"}
        assert set(result.keys()) == expected_dims

    def test_solvency_debt_ratio_green(self, sample_metrics):
        """资产负债率 35% → 绝对值<40% → 🟢"""
        result = assess_traffic_lights(sample_metrics)
        assert result["solvency"]["资产负债率"]["2024"]["absolute"] == "green"

    def test_solvency_debt_ratio_change(self, sample_metrics):
        """资产负债率 35→40→45, 2024同比=(35-40)/40=-12.5% → 🟢"""
        result = assess_traffic_lights(sample_metrics)
        assert result["solvency"]["资产负债率"]["2024"]["change"] == "green"

    def test_debt_ratio_yellow_abs(self, sample_metrics):
        """修改为 50%（40-65%区间）→ 🟡"""
        m = sample_metrics.copy()
        m["solvency"]["资产负债率"]["2024"] = 50.0
        result = assess_traffic_lights(m)
        assert result["solvency"]["资产负债率"]["2024"]["absolute"] == "yellow"

    def test_debt_ratio_red_abs(self, sample_metrics):
        """修改为 70%（>65%）→ 🔴"""
        m = sample_metrics.copy()
        m["solvency"]["资产负债率"]["2024"] = 70.0
        result = assess_traffic_lights(m)
        assert result["solvency"]["资产负债率"]["2024"]["absolute"] == "red"

    def test_final_is_max(self, sample_metrics):
        """最终灯色 = max(绝对值灯, 变化率灯)。"""
        m = sample_metrics.copy()
        m["solvency"]["资产负债率"]["2024"] = 70.0  # 绝对值🔴
        # 变化率 = (70-40)/40 = 75% → 🔴
        result = assess_traffic_lights(m)
        assert result["solvency"]["资产负债率"]["2024"]["final"] == "red"

    def test_none_metric_skipped(self, sample_metrics):
        """应收账款周转率为 None 时跳过。"""
        result = assess_traffic_lights(sample_metrics)
        # None 值不应有评判结果，或应有明确标记
        entry = result["efficiency"]["应收账款周转率"]["2024"]
        assert entry["final"] is None or "absolute" not in entry or entry["absolute"] is None


# ── 健康度评分 ──


class TestHealthScore:
    def test_all_green(self):
        lights = {
            "solvency": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "green"}},
                "指标3": {"2024": {"final": "green"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "green"}},
            },
            "profitability": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "green"}},
                "指标3": {"2024": {"final": "green"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "green"}},
            },
            "efficiency": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "green"}},
                "指标3": {"2024": {"final": "green"}},
                "指标4": {"2024": {"final": "green"}},
            },
            "cashflow": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "green"}},
                "指标3": {"2024": {"final": "green"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "green"}},
                "指标6": {"2024": {"final": "green"}},
            },
        }
        score = compute_health_score(lights, "2024")
        assert isclose(score["total"], 100.0)
        assert score["rating"] == "healthy"

    def test_all_red(self):
        lights = {
            "solvency": {
                "指标1": {"2024": {"final": "red"}},
                "指标2": {"2024": {"final": "red"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "red"}},
                "指标5": {"2024": {"final": "red"}},
            },
            "profitability": {
                "指标1": {"2024": {"final": "red"}},
                "指标2": {"2024": {"final": "red"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "red"}},
                "指标5": {"2024": {"final": "red"}},
            },
            "efficiency": {
                "指标1": {"2024": {"final": "red"}},
                "指标2": {"2024": {"final": "red"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "red"}},
            },
            "cashflow": {
                "指标1": {"2024": {"final": "red"}},
                "指标2": {"2024": {"final": "red"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "red"}},
                "指标5": {"2024": {"final": "red"}},
                "指标6": {"2024": {"final": "red"}},
            },
        }
        score = compute_health_score(lights, "2024")
        assert isclose(score["total"], 0.0)
        assert score["rating"] == "warning"

    def test_mixed_gives_middle_score(self):
        lights = {
            "solvency": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "yellow"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "yellow"}},
            },
            "profitability": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "green"}},
                "指标3": {"2024": {"final": "green"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "green"}},
            },
            "efficiency": {
                "指标1": {"2024": {"final": "yellow"}},
                "指标2": {"2024": {"final": "yellow"}},
                "指标3": {"2024": {"final": "yellow"}},
                "指标4": {"2024": {"final": "yellow"}},
            },
            "cashflow": {
                "指标1": {"2024": {"final": "red"}},
                "指标2": {"2024": {"final": "red"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "red"}},
                "指标5": {"2024": {"final": "red"}},
                "指标6": {"2024": {"final": "red"}},
            },
        }
        score = compute_health_score(lights, "2024")
        # 偿债: (1+0.5+0+1+0.5)/5 * 25 = 15.0
        # 盈利: 5*1.0/5 * 25 = 25.0
        # 运营: 4*0.5/4 * 25 = 12.5
        # 现金流: 0/6 * 25 = 0.0
        # 总计: 15+25+12.5+0 = 52.5
        assert isclose(score["total"], 52.5)
        assert score["rating"] == "warning"

    def test_per_dimension_scores(self):
        lights = {
            "solvency": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "green"}},
                "指标3": {"2024": {"final": "green"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "green"}},
            },
            "profitability": {
                "指标1": {"2024": {"final": "yellow"}},
                "指标2": {"2024": {"final": "yellow"}},
                "指标3": {"2024": {"final": "yellow"}},
                "指标4": {"2024": {"final": "yellow"}},
                "指标5": {"2024": {"final": "yellow"}},
            },
            "efficiency": {
                "指标1": {"2024": {"final": "red"}},
                "指标2": {"2024": {"final": "red"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "red"}},
            },
            "cashflow": {
                "指标1": {"2024": {"final": "green"}},
                "指标2": {"2024": {"final": "yellow"}},
                "指标3": {"2024": {"final": "red"}},
                "指标4": {"2024": {"final": "green"}},
                "指标5": {"2024": {"final": "yellow"}},
                "指标6": {"2024": {"final": "red"}},
            },
        }
        score = compute_health_score(lights, "2024")
        assert isclose(score["dimensions"]["solvency"], 25.0)
        assert isclose(score["dimensions"]["profitability"], 12.5)
        assert isclose(score["dimensions"]["efficiency"], 0.0)
        # 现金流: 2绿(2*4.167) + 2黄(2*2.083) + 2红(0) = 12.5
        assert isclose(score["dimensions"]["cashflow"], 12.5)


# ── 安全地板规则 ──


class TestSafetyFloor:
    """绝对值远超优良阈值时，变化率灯色降为绿色。"""

    def test_extreme_value_unchanged_by_decline(self):
        """利息覆盖倍数 3994 vs 8266，下降 51.7%，但 3994 >> 60(6*10)→ 变化率覆盖为绿。"""
        m = {
            "solvency": {
                "利息覆盖倍数": {"2024": 3994.0, "2023": 8266.0},
            },
            "profitability": {},
            "efficiency": {},
            "cashflow": {},
        }
        result = assess_traffic_lights(m)
        assert result["solvency"]["利息覆盖倍数"]["2024"]["change"] == "green"
        assert result["solvency"]["利息覆盖倍数"]["2024"]["final"] == "green"

    def test_not_applied_near_threshold(self):
        """利息覆盖倍数 7 vs 15，下降 53%，但 7 < 60 → 安全地板不生效。"""
        m = {
            "solvency": {
                "利息覆盖倍数": {"2024": 7.0, "2023": 15.0},
            },
            "profitability": {},
            "efficiency": {},
            "cashflow": {},
        }
        result = assess_traffic_lights(m)
        assert result["solvency"]["利息覆盖倍数"]["2024"]["change"] == "red"
        assert result["solvency"]["利息覆盖倍数"]["2024"]["final"] == "red"

    def test_not_applied_when_abs_yellow(self):
        """绝对值黄色时，安全地板不介入。"""
        m = {
            "solvency": {
                "利息覆盖倍数": {"2024": 4.0, "2023": 9.0},
            },
            "profitability": {},
            "efficiency": {},
            "cashflow": {},
        }
        result = assess_traffic_lights(m)
        assert result["solvency"]["利息覆盖倍数"]["2024"]["absolute"] == "yellow"
        # 变化率 (4-9)/9 = -55.6% → red
        assert result["solvency"]["利息覆盖倍数"]["2024"]["change"] == "red"

    def test_applied_for_lower_is_better(self):
        """资产负债率 1.0% (green_thresh=40, 40/10=4, 1.0<=4) → 覆盖。"""
        m = {
            "solvency": {
                "资产负债率": {"2024": 1.0, "2023": 3.0},
            },
            "profitability": {},
            "efficiency": {},
            "cashflow": {},
        }
        result = assess_traffic_lights(m)
        assert result["solvency"]["资产负债率"]["2024"]["change"] == "green"
        assert result["solvency"]["资产负债率"]["2024"]["final"] == "green"

    def test_preserves_green_change(self):
        """变化率已是绿色时直接返回。"""
        result = _apply_safety_floor("利息覆盖倍数", 3994.0, "green", "green")
        assert result == "green"

    def test_zero_green_threshold_skip(self):
        """净债务/EBITDA green_threshold=0，跳过安全地板。"""
        # green_thresh=0, higher_is_better=False → 除以零风险，应跳过
        result = _apply_safety_floor("净债务/EBITDA", -0.5, "green", "red")
        assert result == "red"
