"""考卷生成测试：分层抽样 + 对抗子集 + 防锚定列删除。"""

import csv
import json
from pathlib import Path

from evals.claim_benchmark import build_benchmark as bb


def _raw_claim(
    field_ref: str, claim_type: str = "numerical", stated=1.0, interp="", trace_id="t1"
) -> dict:
    return {
        "claim": {
            "claim_type": claim_type,
            "source_type": "data",
            "field_ref": field_ref,
            "stated_value": stated,
            "interpretation": interp,
        },
        "verifier_status": "PASS",
        "ground_truth": 10.0,
        "delta": 0.1,
        "coverage_gap": False,
        "trace_id": trace_id,
        "stock_code": "600001",
        "stock_name": "某股",
        "trace_timestamp": "2026-08-20T00:00:00+00:00",
        "trace_version": "pre_fix",
        "rejudged_status": "PASS",
    }


def _write_pool(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _make_pool(numerical: int, computational: int, comparative: int) -> list[dict]:
    rows = []
    for i in range(numerical):
        # 8 个 trace 分摊，避免 per-trace cap（8）饿死抽样
        r = _raw_claim(f"technical_indicators.MA.5.{i % 60}", stated=10.0 + i, trace_id=f"t{i % 8}")
        rows.append(r)
    for i in range(computational):
        rows.append(
            _raw_claim(
                "dupont_tree.roe.2025",
                claim_type="computational",
                stated=1.0 + i * 0.1,
                trace_id=f"t{i % 8}",
            )
        )
    for _ in range(comparative):
        rows.append(
            {
                **_raw_claim("solvency_metrics.资产负债率.2024", stated="greater_than"),
                "claim": {
                    "claim_type": "comparative",
                    "source_type": "data",
                    "field_ref": "solvency_metrics.资产负债率.2024",
                    "field_ref_b": "solvency_metrics.资产负债率.2023",
                    "stated_value": "greater_than",
                    "interpretation": "2024 高于 2023",
                },
            }
        )
    return rows


class TestBuild:
    def test_stratified_sample_and_session_cap(self, tmp_path: Path):
        pool = _make_pool(numerical=60, computational=20, comparative=20)
        # 8 个 trace 分摊（cap 8/会话），20 条抽样应命中 cap 且不饿死
        in_path = tmp_path / "in.jsonl"
        _write_pool(in_path, pool)
        prefix = tmp_path / "benchmark_v1"
        bb.build(in_path, 20, 0, 0, seed=1, out_prefix=prefix)
        entries = [
            json.loads(line)
            for line in (tmp_path / "benchmark_v1.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(entries) == 20
        per_trace: dict[str, int] = {}
        for e in entries:
            per_trace[e["trace_id"]] = per_trace.get(e["trace_id"], 0) + 1
        assert max(per_trace.values()) <= bb.MAX_PER_TRACE
        assert {e["claim"]["claim_type"] for e in entries} >= {
            "numerical",
            "computational",
            "comparative",
        }

    def test_near_miss_and_hedged_subsets(self, tmp_path: Path):
        # clean=0 隔离对抗子集：不与 clean 抽样竞争同一行（确定性）
        nm = _raw_claim("profitability_metrics.毛利率.2025", stated=10.0)
        nm["ground_truth"], nm["delta"] = 10.0, 0.1  # 相对 1% → 擦边带内
        hd = _raw_claim("solvency_metrics.资产负债率.2025", stated=10.0, interp="约为 10%")
        hd["ground_truth"], hd["delta"] = 10.0, 0.8  # 相对 8% → 不在擦边带（避免子集重叠）
        in_path = tmp_path / "in.jsonl"
        _write_pool(in_path, [nm, hd])
        prefix = tmp_path / "b"
        bb.build(in_path, 0, 1, 1, seed=1, out_prefix=prefix)
        entries = [
            json.loads(line)
            for line in (tmp_path / "b.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        by_subset: dict[str, list[str]] = {}
        for e in entries:
            for s in e["subsets"]:
                by_subset.setdefault(s, []).append(e["entry_id"])
        assert "near_miss" in by_subset and "hedged" in by_subset
        assert len(entries) == 2  # 子集互斥

    def test_for_labeling_drops_anchoring_columns(self, tmp_path: Path):
        in_path = tmp_path / "in.jsonl"
        _write_pool(in_path, _make_pool(6, 2, 2))
        prefix = tmp_path / "b"
        bb.build(in_path, 8, 0, 0, seed=1, out_prefix=prefix)
        with (tmp_path / "b_for_labeling.csv").open(encoding="utf-8", newline="") as f:
            header = next(csv.reader(f))
        assert "verifier_status" not in header
        assert "expected_label" not in header
        with (tmp_path / "b.csv").open(encoding="utf-8", newline="") as f:
            full_header = next(csv.reader(f))
        assert "verifier_status" in full_header and "expected_label" in full_header

    def test_regression_tag_for_pre_fix_disease(self, tmp_path: Path):
        r = _raw_claim("technical_indicators.MA.5.59", stated=10.0)  # 正索引 = 修复前疾病
        r["trace_version"] = "pre_fix"
        in_path = tmp_path / "in.jsonl"
        _write_pool(in_path, [r])
        prefix = tmp_path / "b"
        bb.build(in_path, 1, 0, 0, seed=1, out_prefix=prefix)
        entries = [
            json.loads(line)
            for line in (tmp_path / "b.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert "regression" in entries[0]["subsets"]
        assert entries[0]["disease"] == "index"
