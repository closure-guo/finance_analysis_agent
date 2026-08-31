"""TDD tests for build_v11.py — 基准集 v1.1 构造规则。"""

import json
from pathlib import Path

from evals.claim_benchmark.build_v11 import build_v11


def _base_rows() -> list[dict]:
    rows = []
    for i in range(30):
        rows.append(
            {
                "entry_id": f"benchmark_v1_{i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.毛利率.2024",
                    "stated_value": 45.2,
                    "interpretation": "毛利率 45.2%",
                },
                "ground_truth": 45.2,
                "delta": 0.0,
                "verifier_status": "PASS",
                "rejudged_status": "PASS",
                "trace_id": f"t{i % 3}",
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "trace_timestamp": "2026-08-30",
                "trace_version": "post_fix",
                "coverage_gap": False,
                "subsets": ["clean"],
                "disease": None,
                "label": "PASS",
            }
        )
    return rows


def _write_pool(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "pool.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def _load(out_prefix: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in out_prefix.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestNearMissV11:
    def test_four_tier_amplitudes_present(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        amps = {e["tamper_amp"] for e in _load(out) if "near_miss" in e["subsets"]}
        assert amps == {0.003, 0.005, 0.007, 0.01}

    def test_half_should_pass(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        nm = [e for e in _load(out) if "near_miss" in e["subsets"]]
        should_pass = sum(1 for e in nm if e["should_pass"])
        assert should_pass == len(nm) / 2

    def test_label_matches_should_pass(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        for e in _load(out):
            if "near_miss" in e["subsets"]:
                assert e["label"] == ("PASS" if e["should_pass"] else "FAIL")
                # 篡改值确实落在声明幅度上（容差重算后与 should_pass 自洽）
                gt = float(e["ground_truth"])
                stated = float(e["claim"]["stated_value"])
                delta = abs(gt - stated)
                tol = max(0.01, abs(gt) * 0.005)
                assert (delta < tol) == e["should_pass"]


class TestSemanticMismatchSubset:
    def test_term_mismatch_labeled_fail(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        terms = [e for e in _load(out) if "semantic_term" in e["subsets"]]
        assert terms, "应生成 semantic_term 风味样本"
        for e in terms:
            assert e["label"] == "FAIL"
            assert e["claim"]["metric_name"] not in (None, "毛利率")

    def test_period_mismatch_labeled_fail(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        periods = [e for e in _load(out) if "semantic_period" in e["subsets"]]
        assert periods
        for e in periods:
            assert e["label"] == "FAIL"
            assert e["claim"]["period"] not in (None, "2024")

    def test_control_keeps_original_label(self, tmp_path):
        pool = _write_pool(tmp_path, _base_rows())
        out = tmp_path / "benchmark_v11"
        build_v11(pool, out, near_miss_n=20, semantic_n=12, seed=42)
        controls = [e for e in _load(out) if "semantic_control" in e["subsets"]]
        assert controls
        for e in controls:
            assert e["label"] == "PASS"
            assert e["claim"]["metric_name"] == "毛利率"
            assert e["claim"]["period"] == "2024"
