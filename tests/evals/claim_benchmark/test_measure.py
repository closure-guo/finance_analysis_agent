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


class TestMeasureV11Subsets:
    def _entries(self) -> list[dict]:
        def near_miss(label: str, stated: float, gt: float, i: int) -> dict:
            return {
                "entry_id": f"benchmark_v11_{i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "stated_value": stated,
                    "interpretation": "x",
                },
                "ground_truth": gt,
                "delta": abs(gt - stated),
                "subsets": ["near_miss"],
                "should_pass": label == "PASS",
                "label": label,
            }

        def semantic(metric_name: str, label: str, i: int) -> dict:
            return {
                "entry_id": f"benchmark_v11_{100 + i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "stated_value": 45.2,
                    "interpretation": "x",
                    "metric_name": metric_name,
                },
                "ground_truth": 45.2,
                "delta": 0.0,
                "subsets": ["semantic_mismatch", "semantic_term"],
                "label": label,
            }

        entries = [
            near_miss("PASS", 45.2 * 1.003, 45.2, 0),  # 容差内 → 复判 PASS
            near_miss("FAIL", 45.2 * 1.01, 45.2, 1),  # 过线 → 复判 FAIL
            semantic("净利率", "FAIL", 0),  # 术语错配 → 复判 FAIL（检出）
        ]
        return entries

    def test_near_miss_split_disclosed(self):
        from evals.claim_benchmark.measure import measure

        rep = measure(self._entries())
        assert rep["near_miss_over_line_recall"] == 1.0  # 过线 1/1 检出
        assert rep["near_miss_in_line_fp_rate"] == 0.0  # 线内 0 误报

    def test_semantic_detection_gate(self):
        from evals.claim_benchmark.measure import measure

        rep = measure(self._entries())
        assert rep["semantic_mismatch_detection"] == 1.0
        assert rep["semantic_gate"] == {"gate": 0.9, "passed": True}

    def test_semantic_gate_fails_below_90(self):
        from evals.claim_benchmark.measure import measure

        entries = self._entries()
        # 再加 9 条术语正确但 label=FAIL 的构造（复判 PASS → 未检出）
        for i in range(9):
            entries.append(
                {
                    "entry_id": f"benchmark_v11_{200 + i:04d}",
                    "claim": {
                        "claim_type": "numerical",
                        "source_type": "data",
                        "field_ref": "profitability_metrics.毛利率.2024",
                        "stated_value": 45.2,
                        "interpretation": "x",
                        "metric_name": "毛利率",
                    },
                    "ground_truth": 45.2,
                    "delta": 0.0,
                    "subsets": ["semantic_mismatch", "semantic_term"],
                    "label": "FAIL",
                }
            )
        rep = measure(entries)
        assert rep["semantic_mismatch_detection"] == 0.1
        assert rep["semantic_gate"]["passed"] is False
