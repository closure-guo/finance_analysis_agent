"""校验器准度测量与门禁（spec evaluation「校验器准度测量与门禁」）。

FAIL 为正类（校验器的可执行产出就是拦截错误 claim）。门禁：整体 F1 ≥ 0.90
方可宣称校验结果可信；擦边（±5%）与 hedged 子集的分项召回（子集内 FAIL 类
召回）单独披露，不设硬门禁；子集内整体一致率另字段披露。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from evals.claim_benchmark.fixtures import build_state
from evals.claim_benchmark.schema import BenchmarkEntry, load_entries, load_meta
from finance_agent.citation import Claim, verify_claims

F1_GATE = 0.90


class AccuracyReport(BaseModel):
    n: int
    precision: float
    recall: float
    f1: float
    f1_ci: tuple[float, float]
    accuracy: float
    borderline_recall: float | None = None
    hedged_recall: float | None = None
    borderline_subset_agreement: float | None = None
    hedged_subset_agreement: float | None = None
    gate_passed: bool
    gate_note: str


def _predicted(entry: BenchmarkEntry, state: dict) -> str:
    claim = Claim.model_validate(entry.claim)
    return verify_claims([claim], state)[0].status


def measure(entries: list[BenchmarkEntry], *, seed: int = 42) -> AccuracyReport:
    states: dict[str, dict] = {}
    rows: list[tuple[str, str, list[str]]] = []  # (label, predicted, subsets)
    for e in entries:
        if e.state_key not in states:
            states[e.state_key] = build_state(e.state_key)
        rows.append((e.label_final, _predicted(e, states[e.state_key]), e.subsets))

    tp = sum(1 for lab, pr, _ in rows if lab == "FAIL" and pr == "FAIL")
    fp = sum(1 for lab, pr, _ in rows if lab != "FAIL" and pr == "FAIL")
    fn = sum(1 for lab, pr, _ in rows if lab == "FAIL" and pr != "FAIL")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = sum(1 for lab, pr, _ in rows if lab == pr) / len(rows) if rows else 0.0

    # F1 的 bootstrap CI：按 entry 重采样，TP/FP/FN 逐次重算（spec：P/R/F1 带 95% CI）
    if rows:
        fail_labels = np.array([1.0 if lab == "FAIL" else 0.0 for lab, _, _ in rows])
        fail_preds = np.array([1.0 if pr == "FAIL" else 0.0 for _, pr, _ in rows])
        rng = np.random.default_rng(seed)
        n = len(rows)
        idx = rng.integers(0, n, size=(2_000, n))
        f1_samples: list[float] = []
        for row in idx:
            lab_s = fail_labels[row]
            pr_s = fail_preds[row]
            tp_s = int(np.sum((lab_s == 1) & (pr_s == 1)))
            fp_s = int(np.sum((lab_s == 0) & (pr_s == 1)))
            fn_s = int(np.sum((lab_s == 1) & (pr_s == 0)))
            p_s = tp_s / (tp_s + fp_s) if tp_s + fp_s else 0.0
            r_s = tp_s / (tp_s + fn_s) if tp_s + fn_s else 0.0
            f1_samples.append(2 * p_s * r_s / (p_s + r_s) if p_s + r_s else 0.0)
        lo = float(np.percentile(f1_samples, 2.5))
        hi = float(np.percentile(f1_samples, 97.5))
    else:
        lo = hi = 0.0

    def _subset_fail_recall(name: str) -> float | None:
        """子集内 FAIL 类召回：子集中 label==FAIL 的条目里 predicted==FAIL 的比例。

        子集无 FAIL 标注条目时召回不可计算，返回 None（区别于子集为空）。
        """
        sub = [(lab, pr) for lab, pr, ss in rows if name in ss]
        fails = [pr for lab, pr in sub if lab == "FAIL"]
        if not fails:
            return None
        return sum(1 for pr in fails if pr == "FAIL") / len(fails)

    def _subset_agreement(name: str) -> float | None:
        sub = [(lab, pr) for lab, pr, ss in rows if name in ss]
        if not sub:
            return None
        return sum(1 for lab, pr in sub if lab == pr) / len(sub)

    borderline = _subset_fail_recall("borderline")
    hedged = _subset_fail_recall("hedged")
    borderline_agreement = _subset_agreement("borderline")
    hedged_agreement = _subset_agreement("hedged")
    gate_passed = f1 >= F1_GATE
    return AccuracyReport(
        n=len(rows),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        f1_ci=(round(lo, 4), round(hi, 4)),
        accuracy=round(accuracy, 4),
        borderline_recall=None if borderline is None else round(borderline, 4),
        hedged_recall=None if hedged is None else round(hedged, 4),
        borderline_subset_agreement=(
            None if borderline_agreement is None else round(borderline_agreement, 4)
        ),
        hedged_subset_agreement=None if hedged_agreement is None else round(hedged_agreement, 4),
        gate_passed=gate_passed,
        gate_note=(
            "校验器准度可信（F1 ≥ 0.90）"
            if gate_passed
            else "校验器自身准度未达标：下游 FAIL 判定须在评估报告中标注此状态"
        ),
    )


def main() -> None:
    meta = load_meta()
    entries = load_entries()
    report = measure(entries)
    payload = {
        "benchmark_version": meta.version,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        **report.model_dump(),
        "disclosure": (
            "borderline_recall/hedged_recall 为子集内 FAIL 类召回"
            "（子集中 label==FAIL 的条目里预测为 FAIL 的比例；子集无 FAIL 条目时为 null）；"
            "borderline_subset_agreement/hedged_subset_agreement 为子集内整体一致率（原口径）。"
            "擦边子集（stated_value 真值 ±5% 内对抗 claim）与 hedged 子集（约/可能/接近措辞）"
            "均单独披露，不设硬门禁。"
        ),
    }
    out_dir = Path("reports/claim_benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"accuracy-v{meta.version}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"准度报告已写入 {path}")


if __name__ == "__main__":
    main()
