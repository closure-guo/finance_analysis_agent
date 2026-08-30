"""准度测量测试：F1 门禁、near_miss 检出率、hedged 假阳率、回归子集披露。"""

import json
from pathlib import Path

from evals.claim_benchmark import measure


def _entry(
    eid: str,
    label: str,
    subsets: list[str],
    gt=10.0,
    delta=0.0,
    field_ref="x",
    claim_type: str = "numerical",
) -> dict:
    """复判可构造：数值型 claim，复判结果由 rejudge_claim(gt, delta) 决定。"""
    return {
        "entry_id": eid,
        "claim": {
            "claim_type": claim_type,
            "source_type": "data",
            "field_ref": field_ref,
            "stated_value": 10.0,
            "interpretation": "",
        },
        "ground_truth": gt,
        "delta": delta,
        "subsets": subsets,
        "label": label,
        "verifier_status": label,
        "rejudged_status": "PASS",
    }


def _write_entries(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


class TestMeasure:
    def test_perfect_match_passes_gate(self):
        rep = measure.measure(
            [
                _entry("a", "FAIL", [], delta=1.0),  # 复判 FAIL
                _entry("b", "PASS", [], delta=0.001),  # 复判 PASS
            ]
        )
        assert rep["f1"] == 1.0
        assert rep["gate"]["passed"]

    def test_missed_fail_fails_gate(self):
        rep = measure.measure(
            [
                _entry("a", "FAIL", [], delta=0.001),  # 复判 PASS → FN
                _entry("b", "FAIL", [], delta=1.0),
                _entry("c", "FAIL", [], delta=1.0),
            ]
        )
        assert rep["recall"] == round(2 / 3, 4)
        assert not rep["gate"]["passed"]

    def test_near_miss_recall_report(self):
        rep = measure.measure(
            [
                _entry("a", "FAIL", ["near_miss"], delta=0.04),  # 复判 PASS（容差内）→ FN
                _entry("b", "FAIL", ["near_miss"], delta=0.1),  # 复判 FAIL → TP
            ]
        )
        assert rep["near_miss_recall"] == 0.5

    def test_hedged_fp_rate_report(self):
        rep = measure.measure(
            [
                _entry("a", "PASS", ["hedged"], delta=0.05),  # 复判 FAIL ∧ 人工非 FAIL → FP
                _entry("b", "PASS", ["hedged"], delta=0.001),  # 复判 PASS
            ]
        )
        assert rep["hedged_fp_rate"] == 0.5

    def test_regression_excluded_and_disclosed(self):
        reg = _entry(
            "r", "PASS", ["regression"], gt=None, delta=None, field_ref="盈利能力.毛利率.2025"
        )
        reg["claim"]["field_ref"] = "盈利能力.毛利率.2025"
        core = _entry("c", "FAIL", [], delta=1.0)
        rep = measure.measure([reg, core])
        assert rep["n_core"] == 1
        assert rep["excluded_breakdown"]["regression"] == 1
        assert rep["excluded_breakdown"]["regression_label_dist"] == {"PASS": 1}

    def test_empty_label_refused(self, tmp_path: Path, capsys):
        path = tmp_path / "in.jsonl"
        _write_entries(path, [{"entry_id": "e1", "claim": {}, "label": None}])
        try:
            measure.main()
        except SystemExit as e:
            assert e.code == 2
        else:  # pragma: no cover
            raise AssertionError("空 label 应拒绝测量")
