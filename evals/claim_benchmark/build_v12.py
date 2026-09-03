#!/usr/bin/env python
"""基准集 v1.2 生成（refine-citation-coverage-v3 门禁盲区修复）。

v3 新增校验路径在 v1.1 无样本（baseline-v2 r3 同款结构：门禁测不到现役规则）：
- growth_rounding（B/D 类，D2/D4 取整感知容差）：growth_rates 数值 claim，
  stated 为整数百分比取整值 → 标签 PASS（0.5pp ≤ ABS_TOL）；真错变体 → FAIL；
- comparative_base（C 类，D3 双端）：comparative 声明 stated_value_b 正确 → PASS、
  缺失 → FAIL（基期裸奔）、错值 → FAIL。

标签构造即确定（同 v1.1 口径，不经 LLM）。基于 v1.1 全集追加，不改旧条目。

用法：
    uv run python evals/claim_benchmark/build_v12.py \
        --input evals/claim_benchmark/data/benchmark_v11.jsonl \
        --out-prefix evals/claim_benchmark/data/benchmark_v12
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from finance_agent.citation import ABS_TOL, REL_TOL  # noqa: E402


def _growth_samples() -> list[dict]:
    """D2/D4 取整感知容差样本（growth_rates 数值 claim）。"""
    out = []
    # (dim, metric, truth, stated, label, note)
    cases = [
        ("solvency", "净债务/EBITDA", -3.676, -3.68, "PASS", "整数取整 -368%（0.4pp）"),
        ("cashflow", "FCF", 0.504, 0.50, "PASS", "50.4%→50%（0.4pp）"),
        (
            "profitability",
            "归母净利润",
            1.0878,
            1.08,
            "PASS",
            "108.78%→108%（0.78pp 分数制 0.0078 < 0.01）",
        ),
        ("efficiency", "利息覆盖倍数", -0.52, -0.52, "PASS", "精确命中"),
        # 真错变体（差 100pp / 明显错值）
        ("solvency", "净债务/EBITDA", -3.676, -2.68, "FAIL", "真错：-268% vs 真值 -367.6%"),
        ("cashflow", "FCF", 0.504, 0.90, "FAIL", "真错：90% vs 真值 50.4%"),
        ("profitability", "归母净利润", 1.0878, 0.98, "FAIL", "真错：98% vs 真值 108.78%"),
    ]
    for i, (dim, metric, gt, stated, label, note) in enumerate(cases):
        out.append(
            {
                "entry_id": f"benchmark_v12_growth_{i:04d}",
                "claim": {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": f"growth_rates.{dim}.{metric}",
                    "stated_value": stated,
                    "interpretation": f"{metric} 变化率（{note}）",
                    "metric_name": metric,
                },
                "ground_truth": gt,
                "delta": abs(gt - stated),
                "subsets": ["growth_rounding"],
                "label": label,
            }
        )
    return out


def _comparative_samples() -> list[dict]:
    """D3 comparative 双端样本。"""
    out = []
    cases = [
        # (stated_value_b, label, note) —— 基期真值 21.93，当期 19.07（equal_to 不成立，
        # 用 greater/less 不可离线判；当期 delta 取 0.005 使 equal_to 成立）
        (21.93, "PASS", "基期正确"),
        (None, "FAIL", "基期裸奔（field_ref_b 设而 stated_value_b 缺）"),
        (28.0, "FAIL", "基期错值（28.0 vs 真值 21.93）"),
        (21.9, "PASS", "基期约数（21.9 vs 21.93，0.03 < 0.1097 容差）"),
    ]
    for i, (svb, label, note) in enumerate(cases):
        out.append(
            {
                "entry_id": f"benchmark_v12_compbase_{i:04d}",
                "claim": {
                    "claim_type": "comparative",
                    "source_type": "data",
                    "field_ref": "profitability_metrics.净利率.2025",
                    "stated_value": "equal_to",
                    "interpretation": f"2025 净利率与基期相等（{note}）",
                    "field_ref_b": "profitability_metrics.净利率.2024",
                    "stated_value_b": svb,
                },
                "ground_truth": 19.07,
                "ground_truth_b": 21.93,
                "delta": 0.005,
                "subsets": ["comparative_base"],
                "label": label,
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="基准集 v1.2 生成")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-prefix", required=True)
    args = ap.parse_args()

    rows = [
        json.loads(line)
        for line in Path(args.input).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    n_base = len(rows)
    added = _growth_samples() + _comparative_samples()
    # 标签自检：与容差公式一致（构造即标签的机器校验）
    for e in added:
        if e["claim"]["claim_type"] == "numerical":
            expect = (
                "PASS"
                if abs(e["ground_truth"] - e["claim"]["stated_value"])
                < max(ABS_TOL, abs(e["ground_truth"]) * REL_TOL)
                else "FAIL"
            )
            if expect != e["label"]:
                raise SystemExit(
                    f"标签自检失败: {e['entry_id']} expect={expect} label={e['label']}"
                )
    rows.extend(added)

    out_jsonl = Path(f"{args.out_prefix}.jsonl")
    out_jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    out_csv = Path(f"{args.out_prefix}.csv")
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry_id", "subset", "label", "field_ref", "stated", "gt"])
        for r in rows:
            w.writerow(
                [
                    r["entry_id"],
                    "+".join(r.get("subsets") or []),
                    r.get("label"),
                    r["claim"].get("field_ref"),
                    r["claim"].get("stated_value"),
                    r.get("ground_truth"),
                ]
            )
    from collections import Counter

    print(
        f"v1.2: 基样 {n_base} + 新增 {len(added)}（growth_rounding 7 / comparative_base 4）= {len(rows)}"
    )
    print("新增标签分布:", dict(Counter(e["label"] for e in added)))
    print(f"输出: {out_jsonl} / {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
