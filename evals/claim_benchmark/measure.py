#!/usr/bin/env python
"""校验器准度测量（verifier-baseline-v1，任务 5）：离线复判 vs 人工标签。

输入 benchmark_v1_labeled.jsonl（含最终 label），对每条重新执行离线复判
（rejudge.rejudge_claim：按当前契约从收割到的 ground_truth/delta 重建
校验器裁决），FAIL 为正类计算整体 P/R/F1（bootstrap 95% CI）。

测量边界（v1.md 判读说明）：
- 复判为 UNVERIFIABLE（gt 缺失 / 比较型方向不可判 / 事件 gt 缺失）或
  regression 疾病样本（修复前 trace 的索引/词表病）不进入 F1 核心——
  解析层无法离线重建，单独披露数量与人工标签分布；
- near_miss 子集「检出率」= 子集内人工 FAIL 条目的复判召回；hedged 子集
  「假阳率」= 子集内复判 FAIL 而人工非 FAIL 的比例（措辞容差盲区）；
- 门禁：整体 F1 ≥ 0.90（不合格 → 打印混淆矩阵 + fp/fn 集中桶回报人工，
  不得调阈值通过）。

用法:
    uv run python evals/claim_benchmark/measure.py \
        --labeled evals/claim_benchmark/data/benchmark_v1_labeled.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from evals.claim_benchmark.rejudge import rejudge_claim  # noqa: E402

F1_GATE = 0.90
MAX_REGRESSION = 0.02
BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 42


@dataclass
class Metrics:
    n: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    f1_ci: tuple[float, float]
    accuracy: float
    gate_passed: bool


@dataclass
class SubsetReport:
    name: str
    n: int
    detail: dict[str, Any] = field(default_factory=dict)


def _rejudge_entry(e: dict) -> str:
    return rejudge_claim(e["claim"], e.get("ground_truth"), e.get("delta"))


def _bootstrap_f1_ci(
    labels: list[str], preds: list[str], seed: int = BOOTSTRAP_SEED
) -> tuple[float, float]:
    fail_lab = np.array([1.0 if lab == "FAIL" else 0.0 for lab in labels])
    fail_pr = np.array([1.0 if p == "FAIL" else 0.0 for p in preds])
    n = len(labels)
    if n == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(BOOTSTRAP_B, n))
    samples: list[float] = []
    for row in idx:
        lab_s, pr_s = fail_lab[row], fail_pr[row]
        tp_s = int(np.sum((lab_s == 1) & (pr_s == 1)))
        fp_s = int(np.sum((lab_s == 0) & (pr_s == 1)))
        fn_s = int(np.sum((lab_s == 1) & (pr_s == 0)))
        p_s = tp_s / (tp_s + fp_s) if tp_s + fp_s else 0.0
        r_s = tp_s / (tp_s + fn_s) if tp_s + fn_s else 0.0
        samples.append(2 * p_s * r_s / (p_s + r_s) if p_s + r_s else 0.0)
    return (float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5)))


def _confusion(labels: list[str], preds: list[str]) -> dict[str, int]:
    c = Counter(zip(labels, preds, strict=True))
    return {
        "tp": c.get(("FAIL", "FAIL"), 0),
        "fp": c.get(("PASS", "FAIL"), 0) + c.get(("UNVERIFIABLE", "FAIL"), 0),
        "fn": c.get(("FAIL", "PASS"), 0) + c.get(("FAIL", "UNVERIFIABLE"), 0),
        "tn": c.get(("PASS", "PASS"), 0)
        + c.get(("UNVERIFIABLE", "UNVERIFIABLE"), 0)
        + c.get(("PASS", "UNVERIFIABLE"), 0)
        + c.get(("UNVERIFIABLE", "PASS"), 0),
    }


def measure(entries: list[dict], f1_gate: float = F1_GATE) -> dict:
    rows = [
        {
            "rejudged": _rejudge_entry(e),
            "label": e.get("label"),
            "subsets": set(e.get("subsets") or []),
            "claim": e["claim"],
            "eid": e["entry_id"],
        }
        for e in entries
    ]

    core = [r for r in rows if r["rejudged"] != "UNVERIFIABLE" and "regression" not in r["subsets"]]
    excluded = [r for r in rows if r["rejudged"] == "UNVERIFIABLE" or "regression" in r["subsets"]]

    labels = [r["label"] for r in core]
    preds = [r["rejudged"] for r in core]
    cm = _confusion(labels, preds)
    n = len(core)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = sum(1 for lab, p in zip(labels, preds, strict=True) if lab == p) / n if n else 0.0
    ci = _bootstrap_f1_ci(labels, preds)

    def _near_miss_recall() -> float | None:
        sub = [r for r in core if "near_miss" in r["subsets"]]
        fails = [r for r in sub if r["label"] == "FAIL"]
        if not fails:
            return None
        return sum(1 for r in fails if r["rejudged"] == "FAIL") / len(fails)

    def _hedged_fp_rate() -> float | None:
        sub = [r for r in core if "hedged" in r["subsets"]]
        if not sub:
            return None
        fp = sum(1 for r in sub if r["rejudged"] == "FAIL" and r["label"] != "FAIL")
        return fp / len(sub)

    # fp/fn 集中桶（供 < 0.90 时人工回报）
    buckets_fp: Counter = Counter()
    buckets_fn: Counter = Counter()
    for r in core:
        if r["label"] != "FAIL" and r["rejudged"] == "FAIL":
            buckets_fp[(r["claim"].get("claim_type"), "+".join(sorted(r["subsets"])))] += 1
        if r["label"] == "FAIL" and r["rejudged"] != "FAIL":
            buckets_fn[(r["claim"].get("claim_type"), "+".join(sorted(r["subsets"])))] += 1

    nm_recall: float | None = _near_miss_recall()
    hedged_fp: float | None = _hedged_fp_rate()

    def _near_miss_split() -> tuple[float | None, float | None]:
        """v1.1 分列：过线检出率（should_fail 召回）与线内误报率（should_pass 误判）。"""
        sub = [r for r in core if "near_miss" in r["subsets"]]
        over = [r for r in sub if r["label"] == "FAIL"]
        inline = [r for r in sub if r["label"] == "PASS"]
        over_recall = sum(1 for r in over if r["rejudged"] == "FAIL") / len(over) if over else None
        inline_fp = (
            sum(1 for r in inline if r["rejudged"] == "FAIL") / len(inline) if inline else None
        )
        return over_recall, inline_fp

    def _semantic_detection() -> float | None:
        """semantic_mismatch 子集检出率（label=FAIL 中复判 FAIL 占比）。"""
        sub = [r for r in rows if "semantic_mismatch" in r["subsets"] and r["label"] == "FAIL"]
        if not sub:
            return None
        return sum(1 for r in sub if r["rejudged"] == "FAIL") / len(sub)

    over_recall, inline_fp = _near_miss_split()
    semantic_det = _semantic_detection()
    regression = [r for r in rows if "regression" in r["subsets"]]
    return {
        "n_core": n,
        "n_excluded": len(excluded),
        "confusion": cm,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "f1_ci_95": [round(ci[0], 4), round(ci[1], 4)],
        "accuracy": round(accuracy, 4),
        "gate": {"f1_gate": f1_gate, "passed": f1 >= f1_gate},
        "near_miss_recall": None if nm_recall is None else round(nm_recall, 4),
        "hedged_fp_rate": None if hedged_fp is None else round(hedged_fp, 4),
        "near_miss_over_line_recall": None if over_recall is None else round(over_recall, 4),
        "near_miss_in_line_fp_rate": None if inline_fp is None else round(inline_fp, 4),
        "semantic_mismatch_detection": None if semantic_det is None else round(semantic_det, 4),
        "semantic_gate": {
            "gate": 0.9,
            "passed": semantic_det is None or semantic_det >= 0.9,
        },
        "excluded_breakdown": {
            "rejudge_unverifiable": sum(1 for r in excluded if r["rejudged"] == "UNVERIFIABLE"),
            "regression": len(regression),
            "regression_label_dist": dict(Counter(r["label"] for r in regression)),
        },
        "fp_buckets": [{"bucket": k, "count": v} for k, v in buckets_fp.most_common(15)],
        "fn_buckets": [{"bucket": k, "count": v} for k, v in buckets_fn.most_common(15)],
    }


def _print_report(rep: dict) -> None:
    print("\n========== 校验器准度报告（离线复判 vs 人工标签）==========")
    print(f"核心样本 n={rep['n_core']}（排除 {rep['n_excluded']}：复判不可得/回归样本）")
    print(f"混淆矩阵: {rep['confusion']}")
    print(
        f"Precision={rep['precision']}  Recall={rep['recall']}  F1={rep['f1']}  "
        f"(95% CI {rep['f1_ci_95']})  Accuracy={rep['accuracy']}"
    )
    print(
        f"门禁 F1 ≥ {rep['gate']['f1_gate']}: {'✅ 通过' if rep['gate']['passed'] else '❌ 未通过'}"
    )
    print(f"near_miss 检出率（子集内人工 FAIL 召回）: {rep['near_miss_recall']}")
    print(f"hedged 假阳率（子集内复判 FAIL ∧ 人工非 FAIL 占比）: {rep['hedged_fp_rate']}")
    print(
        f"near_miss 过线检出率: {rep['near_miss_over_line_recall']}  线内误报率: {rep['near_miss_in_line_fp_rate']}"
    )
    print(
        f"semantic_mismatch 检出率: {rep['semantic_mismatch_detection']}（门禁 ≥ 0.9: {'✅' if rep['semantic_gate']['passed'] else '❌/不适用'}）"
    )
    print(f"排除明细: {rep['excluded_breakdown']}")
    if rep["fp_buckets"] or rep["fn_buckets"]:
        print("fp 集中桶:", rep["fp_buckets"])
        print("fn 集中桶:", rep["fn_buckets"])


def _baseline_regression(rep: dict, baseline_path: Path, max_regression: float) -> dict:
    """与冻结基线比对：当前 F1 相对基线退步超过 max_regression 即不通过。"""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_f1 = float(baseline["f1"])
    delta = round(rep["f1"] - baseline_f1, 4)
    return {
        "baseline_path": str(baseline_path),
        "baseline_f1": baseline_f1,
        "f1_delta": delta,
        "max_regression": max_regression,
        "passed": delta >= -max_regression,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="校验器准度测量")
    ap.add_argument("--labeled", required=True, help="benchmark_v1_labeled.jsonl")
    ap.add_argument("--out-json", default=None, help="可省：报告另存路径")
    ap.add_argument("--gate", type=float, default=F1_GATE, help="F1 门禁阈值（默认 0.90）")
    ap.add_argument(
        "--baseline",
        default=None,
        help="可省：冻结基线 measure JSON（如 results/v11-measure.json），提供则启用退步门禁",
    )
    ap.add_argument(
        "--max-regression",
        type=float,
        default=MAX_REGRESSION,
        help="相对基线的 F1 最大退步容忍（默认 0.02）",
    )
    args = ap.parse_args()

    path = Path(args.labeled)
    entries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    empty = [e["entry_id"] for e in entries if not e.get("label")]
    if empty:
        print(
            f"错误: {len(empty)} 条 entry 无最终 label（{empty[:5]}…），拒绝测量", file=sys.stderr
        )
        return 2

    rep = measure(entries, f1_gate=args.gate)
    if args.baseline:
        rep["baseline_regression"] = _baseline_regression(
            rep, Path(args.baseline), args.max_regression
        )
        br = rep["baseline_regression"]
        print(
            f"基线比对: F1 {br['baseline_f1']} → {rep['f1']}（Δ{br['f1_delta']:+}，"
            f"容忍退步 ≤ {br['max_regression']}）: {'✅ 通过' if br['passed'] else '❌ 退步超限'}"
        )
    _print_report(rep)
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"报告另存 {args.out_json}")
    passed = rep["gate"]["passed"] and rep["semantic_gate"]["passed"]
    if "baseline_regression" in rep:
        passed = passed and rep["baseline_regression"]["passed"]
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
