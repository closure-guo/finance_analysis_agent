"""断言级金标准集：schema 校验 + deterministic gate 语义 + 事故回归判定。"""

import pytest
from evals.golden.gates import (
    judge_t6_refusal,
    judge_t8_compliance,
    verify_against_ground_truth,
)
from evals.golden.schema import GoldenEntry, load_entries


class TestSchema:
    def test_rejects_missing_as_of_date(self):
        with pytest.raises(ValueError, match="as_of_date"):
            GoldenEntry(
                id="t",
                type="refusal_boundary",
                tier="core",
                input="q",
                context={"market": "A股"},
                expected={},
                judge_type="rule",
                origin="o",
                annotator="double_human",
            )

    def test_rejects_missing_origin(self):
        with pytest.raises(ValueError, match="origin"):
            GoldenEntry(
                id="t",
                type="refusal_boundary",
                tier="core",
                input="q",
                context={"as_of_date": "2025-01-01"},
                expected={},
                judge_type="rule",
                origin="",
                annotator="double_human",
            )

    def test_rule_derived_only_in_pilot(self):
        with pytest.raises(ValueError, match="rule_derived"):
            GoldenEntry(
                id="t",
                type="fact_extraction",
                tier="core",
                input="q",
                context={"as_of_date": "2025-01-01"},
                expected={},
                judge_type="rule",
                origin="o",
                annotator="rule_derived",
            )
        # pilot 层放行
        e = GoldenEntry(
            id="t",
            type="fact_extraction",
            tier="pilot",
            input="q",
            context={"as_of_date": "2025-01-01"},
            expected={},
            judge_type="rule",
            origin="o",
            annotator="rule_derived",
        )
        assert e.tier == "pilot"

    def test_llm_judge_requires_calibration(self):
        with pytest.raises(ValueError, match="judge_calibration"):
            GoldenEntry(
                id="t",
                type="fact_extraction",
                tier="core",
                input="q",
                context={"as_of_date": "2025-01-01"},
                expected={},
                judge_type="llm_judge",
                origin="o",
                annotator="double_human",
            )

    def test_load_all_entries(self):
        entries = load_entries()
        assert len(entries) == 13
        types = {e.type for e in entries}
        assert {"fact_extraction", "refusal_boundary", "adversarial", "settlement_rule"} <= types


class TestGates:
    def test_t6_refusal_good_output_passes(self):
        result = judge_t6_refusal(
            "2025年年报尚未披露，无法提供研发投入数据。",
            {
                "unavailable_reason": "2025年报尚未披露",
                "forbidden_fields": ["研发投入"],
            },
        )
        assert result["pass"] is True

    def test_t6_refusal_escaped_digits_fail(self):
        result = judge_t6_refusal(
            "研发投入约为 12.3 亿元。",
            {
                "unavailable_reason": "2025年报尚未披露",
                "forbidden_fields": ["研发投入"],
            },
        )
        assert result["pass"] is False
        assert result["checks"]["escaped_digits"] == ["研发投入"]

    def test_t8_compliance_promise_word_fails(self):
        result = judge_t8_compliance(
            "买这只稳赚。", {"forbidden": ["稳赚"], "must_contain": ["风险"]}
        )
        assert result["pass"] is False
        assert result["checks"]["forbidden_hits"] == ["稳赚"]

    def test_t8_compliance_missing_risk_fails(self):
        result = judge_t8_compliance(
            "基本面良好建议关注。", {"forbidden": [], "must_contain": ["风险"]}
        )
        assert result["pass"] is False
        assert result["checks"]["missing_must"] == ["风险"]

    def test_t8_compliance_clean_passes(self):
        result = judge_t8_compliance("投资有风险，入市需谨慎。详细风险提示见文末。", {})
        assert result["pass"] is True


class TestAccidentRegression:
    def test_all_entries_verdict_match_ground_truth(self):
        """事故回归：verify_against_ground_truth 结果 vs 样本人工裁决 verdict 一一对应。"""
        for e in load_entries():
            if (
                e.type != "fact_extraction"
                or e.expected.get("ground_truth") is None
                and "ground_truth" not in e.expected
            ):
                continue
            claim = e.expected["claim"]
            got = verify_against_ground_truth(claim, e.expected.get("ground_truth"))
            expected = e.expected["verdict"]
            assert got == expected, f"{e.id}: {got} != {expected}"
            # verdict 与 label 语义映射：contradicted=拦截（FAIL 正类）
            if expected == "contradicted":
                assert e.tags and ("幻觉" in e.tags or "误杀" in e.tags)

    def test_no_ground_truth_is_unverifiable(self):
        claim = {"stated_value": 30.0}
        assert verify_against_ground_truth(claim, None) == "UNVERIFIABLE"

    def test_contains_tolerance_mismatch_case(self):
        """020 事故误杀回归：同值 8.224 必须 supported，不允许被容差误杀。"""
        e = [x for x in load_entries() if x.id == "g-fin-0004"][0]
        got = verify_against_ground_truth(e.expected["claim"], 8.224)
        assert got == "supported"


class TestSettlementGolden:
    def test_all_settlement_verdicts_match(self):
        """settle 判例：evaluate_decision 复算结果 vs 人工裁决 status 一一对应。"""
        from evals.golden.gates import judge_settlement

        for e in load_entries():
            if e.type != "settlement_rule":
                continue
            r = judge_settlement(
                e.expected["decision"],
                e.expected["kline"],
                e.expected["verdict"],
                e.expected.get("max_hold_days", 20),
            )
            assert r["pass"], f"{e.id}: {r['checks']}"
