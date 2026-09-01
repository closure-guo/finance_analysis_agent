#!/usr/bin/env python
"""基准集 v1.1 生成（harden-citation-semantic-coverage）：

- near_miss 重构：篡改幅度 ±{0.3%, 0.5%, 0.7%, 1%} 四档探容差边界，
  50% should_pass（容差内，标签 PASS）→ 同时测量漏检与误报；
- 新增 semantic_mismatch 子集：数值/field_ref 正确但术语或期次张冠李戴
  （标签 FAIL），配对照组（正确申报，沿用原 label）测误报；
- 标签由规则确定（篡改后按数值型容差公式重算 should_pass；语义错配构造
  即 FAIL），不经 LLM 标注——合成样本标签确定性，披露于输出统计。

用法:
    uv run python evals/claim_benchmark/build_v11.py \
        --input evals/claim_benchmark/data/benchmark_v1_labeled.jsonl \
        --near-miss 40 --semantic 30 --seed 42 \
        --out-prefix evals/claim_benchmark/data/benchmark_v11
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from finance_agent.metric_vocab import (  # noqa: E402
    _METRIC_ALIASES,
    canonical_metric,
    field_ref_metric_segments,
    field_ref_period_segment,
)

TAMPER_AMPS = (0.003, 0.005, 0.007, 0.01)


def _tol_pass(stated: float, gt: float) -> bool:
    """数值型容差公式镜像（与 citation.py 数值型一致）。"""
    return abs(gt - stated) < max(0.01, abs(gt) * 0.005)


def _eligible_clean(rows: list[dict]) -> list[dict]:
    """label==PASS、gt 数值可用、clean 子集的基样。"""
    out = []
    for r in rows:
        if r.get("label") != "PASS" or "clean" not in (r.get("subsets") or []):
            continue
        try:
            float(r["ground_truth"])
        except (TypeError, ValueError):
            continue
        out.append(r)
    return out


def _make_near_miss(base: list[dict], n: int, rng: random.Random) -> list[dict]:
    """四档篡改 ± 双向 + 50/50 should_pass 配额（候选生成后按配额抽取）。

    每个基样 × 每档幅度 × 双向 ± 生成候选，使 should_pass 池充裕以满足
    50/50 配额（「四档双向」语义：每档幅度均出现 + 与 - 方向）。
    """
    candidates: list[dict] = []
    for i, row in enumerate(base):
        gt = float(row["ground_truth"])
        amp = TAMPER_AMPS[i % len(TAMPER_AMPS)]
        for sign in (1.0, -1.0):
            tampered = round(gt * (1 + sign * amp), 2)
            should_pass = _tol_pass(tampered, gt)
            entry = {
                **row,
                "claim": {**row["claim"], "stated_value": tampered},
                "delta": abs(gt - tampered),
                "subsets": ["near_miss"],
                "should_pass": should_pass,
                "tamper_amp": amp,
                "label": "PASS" if should_pass else "FAIL",
            }
            candidates.append(entry)
    pass_pool = [c for c in candidates if c["should_pass"]]
    fail_pool = [c for c in candidates if not c["should_pass"]]
    rng.shuffle(pass_pool)
    rng.shuffle(fail_pool)
    half = n // 2
    picked = pass_pool[:half] + fail_pool[: n - half]
    # 池不足时如实披露：用余量互补，占比偏离 50% 由输出统计呈现
    if len(picked) < n:
        rest = [c for c in candidates if c not in picked]
        rng.shuffle(rest)
        picked.extend(rest[: n - len(picked)])
    return picked[:n]


def _semantic_bases(base: list[dict]) -> list[dict]:
    """可注入语义字段的基样：field_ref 有指标段且首个指标段可 canonical 化。"""
    return [
        r
        for r in base
        if field_ref_metric_segments(r["claim"]["field_ref"])
        and canonical_metric(field_ref_metric_segments(r["claim"]["field_ref"])[0])
    ]


def _make_semantic(base: list[dict], n: int, rng: random.Random) -> list[dict]:
    """term / period / control 三小组各 ≈n/3。"""
    vocab = sorted(_METRIC_ALIASES)
    rng.shuffle(base)
    third = n // 3
    out: list[dict] = []
    term_pool = [r for r in base if field_ref_metric_segments(r["claim"]["field_ref"])]
    for row in term_pool[:third]:
        segs = field_ref_metric_segments(row["claim"]["field_ref"])
        correct = canonical_metric(segs[0]) or segs[0]
        wrong = vocab[(vocab.index(correct) + 1) % len(vocab)] if correct in vocab else "净利率"
        if wrong == correct:
            wrong = vocab[(vocab.index(correct) + 2) % len(vocab)]
        out.append(
            {
                **row,
                "claim": {**row["claim"], "metric_name": wrong},
                "subsets": ["semantic_mismatch", "semantic_term"],
                "should_pass": None,
                "tamper_amp": None,
                "label": "FAIL",
            }
        )
    period_pool = [r for r in base if field_ref_period_segment(r["claim"]["field_ref"])]
    for row in period_pool[:third]:
        seg = field_ref_period_segment(row["claim"]["field_ref"]) or ""
        wrong_period = str(int(seg[:4]) - 1) if seg[:4].isdigit() else "1999"
        out.append(
            {
                **row,
                "claim": {
                    **row["claim"],
                    "metric_name": canonical_metric(
                        field_ref_metric_segments(row["claim"]["field_ref"])[0]
                    ),
                    "period": wrong_period,
                },
                "subsets": ["semantic_mismatch", "semantic_period"],
                "should_pass": None,
                "tamper_amp": None,
                "label": "FAIL",
            }
        )
    for row in base[: n - len(out)]:
        segs = field_ref_metric_segments(row["claim"]["field_ref"])
        seg_period = field_ref_period_segment(row["claim"]["field_ref"])
        out.append(
            {
                **row,
                "claim": {
                    **row["claim"],
                    "metric_name": canonical_metric(segs[0]) if segs else None,
                    "period": seg_period,
                },
                "subsets": ["semantic_mismatch", "semantic_control"],
                "should_pass": None,
                "tamper_amp": None,
            }
        )
    return out


def build_v11(
    input_path: Path,
    out_prefix: Path,
    near_miss_n: int,
    semantic_n: int,
    seed: int,
) -> int:
    with input_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rng = random.Random(seed)  # noqa: S311 - 可复现抽样
    base = _eligible_clean(rows)
    print(f"基样池: {len(base)} 条（label=PASS ∧ clean ∧ gt 数值可用）")

    entries = _make_near_miss(base, near_miss_n, rng) + _make_semantic(
        _semantic_bases(base), semantic_n, rng
    )
    for i, e in enumerate(entries):
        e["entry_id"] = f"benchmark_v11_{i:04d}"
        e["verifier_status"] = None
        e["rejudged_status"] = None

    nm = [e for e in entries if "near_miss" in e["subsets"]]
    sp = sum(1 for e in nm if e["should_pass"])
    print(f"near_miss {len(nm)} 条（should_pass {sp} = {sp / max(len(nm), 1):.0%}）")
    print(f"semantic_mismatch {sum(1 for e in entries if 'semantic_mismatch' in e['subsets'])} 条")
    print("[披露] v1.1 标签规则确定（容差公式重算 / 构造即 FAIL），不经 LLM 标注")

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    with out_prefix.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with out_prefix.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "entry_id",
                "subsets",
                "label",
                "should_pass",
                "tamper_amp",
                "field_ref",
                "stated_value",
                "ground_truth",
                "delta",
                "metric_name",
                "period",
            ],
            extrasaction="ignore",
        )
        w.writeheader()
        for e in entries:
            w.writerow(
                {
                    "entry_id": e["entry_id"],
                    "subsets": "+".join(e["subsets"]),
                    "label": e["label"],
                    "should_pass": e.get("should_pass"),
                    "tamper_amp": e.get("tamper_amp"),
                    "field_ref": e["claim"].get("field_ref"),
                    "stated_value": e["claim"].get("stated_value"),
                    "ground_truth": e.get("ground_truth"),
                    "delta": e.get("delta"),
                    "metric_name": e["claim"].get("metric_name"),
                    "period": e["claim"].get("period"),
                }
            )
    print(f"已写: {out_prefix.with_suffix('.jsonl')} / {out_prefix.with_suffix('.csv')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="基准集 v1.1 生成")
    ap.add_argument("--input", required=True)
    ap.add_argument("--near-miss", type=int, default=40)
    ap.add_argument("--semantic", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-prefix", required=True)
    args = ap.parse_args()
    return build_v11(
        Path(args.input), Path(args.out_prefix), args.near_miss, args.semantic, args.seed
    )


if __name__ == "__main__":
    sys.exit(main())
