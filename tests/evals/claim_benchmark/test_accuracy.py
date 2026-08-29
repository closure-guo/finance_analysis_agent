"""准度测量测试：FAIL 为正类；门禁 F1 ≥ 0.90；擦边/模糊子集分项召回显式披露。

_entry 按期望预测值构造真实可校验的 claim（state_v1 真值 40.0）：
PASS→stated 40.0（容差内）、FAIL→stated 60.0（偏离）、UNVERIFIABLE→llm_inference，
使测试经由真实 verify_claims 管线而非 mock 预测。
"""

from evals.claim_benchmark.accuracy import measure
from evals.claim_benchmark.schema import BenchmarkEntry


def _entry(label: str, predicted: str, subsets: list[str] | None = None) -> BenchmarkEntry:
    if predicted == "UNVERIFIABLE":
        claim = {
            "claim_type": "numerical",
            "source_type": "llm_inference",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": 40.0,
            "interpretation": "",
        }
    else:
        claim = {
            "claim_type": "numerical",
            "source_type": "data",
            "field_ref": "solvency_metrics.资产负债率.2024",
            "stated_value": 40.0 if predicted == "PASS" else 60.0,
            "interpretation": "",
        }
    return BenchmarkEntry(
        entry_id="x",
        state_key="state_v1",
        claim=claim,
        label_final=label,
        annotator_a="synthetic-seed",
        annotator_b="synthetic-seed",
        subsets=subsets or [],
    )


class TestMeasure:
    def test_perfect_verifier_passes_gate(self):
        report = measure([_entry("PASS", "PASS"), _entry("FAIL", "FAIL")])
        assert report.precision == 1.0
        assert report.f1 == 1.0
        assert report.gate_passed

    def test_missed_fail_lowers_recall(self):
        report = measure(
            [
                _entry("FAIL", "PASS"),
                _entry("FAIL", "FAIL"),
                _entry("FAIL", "FAIL"),
                _entry("FAIL", "FAIL"),
            ]
        )
        assert report.recall == 0.75
        assert report.f1 < 0.90  # 3/4 召回仍过不了 0.90 门禁（P=1 时 F1≈0.857）

    def test_subsets_recall_reported(self):
        """borderline/hedged_recall 为子集内 FAIL 类召回；子集一致率另字段披露。"""
        report = measure(
            [
                _entry("FAIL", "FAIL", ["borderline"]),
                _entry("FAIL", "PASS", ["borderline"]),
                _entry("PASS", "PASS", ["hedged"]),
                _entry("FAIL", "PASS", ["hedged"]),
            ]
        )
        # 子集内 FAIL 召回：borderline 1/2；hedged 0/1
        assert report.borderline_recall == 0.5
        assert report.hedged_recall == 0.0
        # 子集一致率（原口径，继续披露）：borderline 1/2；hedged 1/2
        assert report.borderline_subset_agreement == 0.5
        assert report.hedged_subset_agreement == 0.5

    def test_subset_without_fail_entries_recall_none(self):
        """子集非空但无 FAIL 标注条目 → FAIL 召回不可计算为 None；一致率照常披露。"""
        report = measure([_entry("PASS", "PASS", ["hedged"]), _entry("PASS", "PASS", ["hedged"])])
        assert report.hedged_recall is None
        assert report.hedged_subset_agreement == 1.0

    def test_empty_subset_recall_is_none(self):
        report = measure([_entry("PASS", "PASS")])
        assert report.borderline_recall is None
        assert report.hedged_recall is None
        assert report.borderline_subset_agreement is None
        assert report.hedged_subset_agreement is None
