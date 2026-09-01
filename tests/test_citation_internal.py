# tests/test_citation_internal.py
"""TDD tests for citation.py — claim 内部一致性（数值回声 + 方向词核对）。"""

from finance_agent.citation import Claim, _extract_numbers, verify_claims


class TestExtractNumbers:
    """归一化口径 fixture（"约 45%"/"45.2%" 同源）。"""

    def test_percent(self):
        assert _extract_numbers("毛利率约 45.2%") == [45.2]
        assert _extract_numbers("毛利率约 45%") == [45.0]

    def test_amount_scaling(self):
        assert _extract_numbers("营收 10.39 亿") == [10.39e8]
        assert _extract_numbers("净利润 1038.76 万元") == [1038.76e4]
        assert _extract_numbers("股价 5.2 元") == [5.2]

    def test_thousands_and_negative(self):
        assert _extract_numbers("营收 1,038.76 亿") == [1038.76e8]
        assert _extract_numbers("同比 -5.2%") == [-5.2]

    def test_plain_number(self):
        assert _extract_numbers("ROE 为 30.5") == [30.5]

    def test_no_number(self):
        assert _extract_numbers("处于行业较高水平") == []


class TestInternalEcho:
    def _state(self) -> dict:
        return {"profitability_metrics": {"毛利率": {"2024": 45.2}}}

    def test_value_two_faces_fails(self):
        """spec 场景：stated 45.2，interpretation 写「约 30%」→ FAIL。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 30%",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"

    def test_hedged_echo_passes(self):
        """「约 45%」与 stated 45.2 在 0.5% 容差内 → PASS。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 45%",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "PASS"

    def test_qualitative_interpretation_skipped(self):
        """interpretation 不含数值 → 跳过回声检查（不误伤定性表述）。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率处于行业较高水平",
        )
        (r,) = verify_claims([claim], self._state())
        assert r.status == "PASS"

    def test_amount_unit_echo_passes(self):
        state = {"income_statement": {"20251231": {"营业总收入": 1038756658.94}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="income_statement.20251231.营业总收入",
            stated_value=1038756658.94,
            interpretation="营业总收入约 10.39 亿",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"


class TestDirectionWords:
    def test_comparative_direction_contradiction_fails(self):
        """greater_than 但 interpretation 只说「下降」→ FAIL。"""
        state = {"profitability_metrics": {"ROE": {"2024": 28.0, "2023": 25.0}}}
        claim = Claim(
            claim_type="comparative",
            source_type="data",
            field_ref="profitability_metrics.ROE.2024",
            stated_value="greater_than",
            interpretation="ROE 同比下降",
            field_ref_b="profitability_metrics.ROE.2023",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"

    def test_growth_negative_but_says_growth_fails(self):
        """增长率 claim 断言 -5.2% 却说「大幅增长」→ FAIL。"""
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="毛利率大幅增长",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"

    def test_negative_growth_correctly_described_passes(self):
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="毛利率同比下降 5.2%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"

    def test_non_growth_metric_negative_value_not_checked(self):
        """非增长类 claim（MACD DIF 负值）说「走弱」不误判——指标段无同比/增速。"""
        state = {"technical_indicators": {"MACD": {"DIF": [-1.0, -44.09]}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="technical_indicators.MACD.DIF.-1",
            stated_value=-44.09,
            interpretation="DIF 为 -44.09，动能走弱",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"

    def test_both_direction_words_skipped(self):
        """正/负向词同时出现（如「营收增长但毛利率下降」）→ 跳过，不赌语义。"""
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="营收增长但毛利率下降 5.2%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"


class TestInternalConsistencyFalsePositiveRegression:
    """incident-级回归：内部一致性误报类（汉森 fixture 残量漂移 5→8 根因钉死）。"""

    def test_yi_face_value_echo_passes(self):
        state = {"quarterly_trend": {"quarters": ["2026Q2"], "net_profit": [0.68]}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="quarterly_trend.net_profit.0",
            stated_value=0.68,
            interpretation="2026Q2净利润约0.68亿元，同比+19.0%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"

    def test_macro_yoy_level_with_trend_commentary_passes(self):
        state = {
            "macro_indicators": {
                "cpi": {
                    "records": [
                        {"月份": "2026年07月份", "全国-同比增长": 0.5},
                        {"月份": "2026年06月份", "全国-同比增长": 1.0},
                        {"月份": "2026年05月份", "全国-同比增长": 1.2},
                    ],
                    "as_of_date": "2026-07-01",
                    "freshness": "fresh",
                }
            }
        }
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="macro_indicators.cpi.2.全国-同比增长",
            stated_value=1.2,
            interpretation="5月CPI同比1.2%，近3个月同比涨幅逐月回落（1.2%→1.0%→0.5%），通胀动能持续走弱",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "PASS"


class TestCoverageGapOnEarlyFail:
    """D5 终审修复：未申报 metric_name/period 的 claim 即便在回声/方向检查提前 FAIL，
    也必须计入覆盖缺口（不得因短路丢失缺口计数）。"""

    def test_echo_fail_counts_gap(self):
        state = {"profitability_metrics": {"毛利率": {"2024": 45.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 30%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"
        assert r.coverage_gap is True

    def test_direction_fail_counts_gap(self):
        state = {"growth_rates": {"profitability": {"毛利率": -5.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="growth_rates.profitability.毛利率",
            stated_value=-5.2,
            interpretation="毛利率同比增长 5.2%",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.bucket == "internal_inconsistency"
        assert r.coverage_gap is True

    def test_echo_fail_with_declared_fields_no_gap(self):
        """对照组：字段申报齐全时回声 FAIL 不计缺口。"""
        state = {"profitability_metrics": {"毛利率": {"2024": 45.2}}}
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=45.2,
            interpretation="毛利率约 30%",
            metric_name="毛利率",
            period="2024",
        )
        (r,) = verify_claims([claim], state)
        assert r.status == "FAIL"
        assert r.coverage_gap is False
