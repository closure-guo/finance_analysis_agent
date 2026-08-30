#!/usr/bin/env python
"""考卷生成：claims_raw.jsonl → 分层抽样 + 对抗子集 → 标注用 CSV/JSONL（任务 3）。

抽样口径（verifier-baseline-v1）：
- clean N 条：按 claim_type 分层（数值型 ~30%、计算型 ~15%、比较型 ~15%，
  其余类型补足）；单一 trace（session）最多 8 条；
- near-miss M 条：擦边对抗子集 —— stated_value 在真值 ±5% 以内（相对
  delta ≤ 5%）且 gt 可得的 claim（容差边界盲区考察）；
- hedged K 条：含「约/接近/左右…」模糊措辞的 claim（措辞容差考察）；
- 子集间互斥（同一 claim 只进一个子集，以 clean 优先）；
- contract_disease 标记（修复前 trace 的索引/词表疾病样本）作为回归考题
  独立 tag，测量时单独披露。

产出（--out-prefix 前缀）：
- <prefix>.jsonl                全量行（含 claim/gt/delta/verifier_status/
  rejudged_status/subsets，供 llm_label / measure 消费）
- <prefix>.csv                  扁平化（含 verifier_status + expected_label=
  rejudged_status，供人工存档核对）
- <prefix>_for_labeling.csv     脱敏标注版（删除 expected_label /
  verifier_status 两列，防锚定）

用法:
    uv run python evals/claim_benchmark/build_benchmark.py \
        --input evals/claim_benchmark/data/claims_raw.jsonl \
        --clean 150 --near-miss 40 --hedged 20 --seed 42 \
        --out-prefix evals/claim_benchmark/data/benchmark_v1
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.claim_benchmark.rejudge import contract_disease, is_hedged  # noqa: E402

# 分层目标（占 clean 总量比例）
TYPE_TARGETS: dict[str, float] = {
    "numerical": 0.30,
    "computational": 0.15,
    "comparative": 0.15,
}
MAX_PER_TRACE = 8
NEAR_MISS_REL = 0.05  # 擦边：相对 delta ≤ 5%

_CSV_COLUMNS = [
    "entry_id",
    "stock_code",
    "stock_name",
    "trace_id",
    "trace_timestamp",
    "trace_version",
    "claim_type",
    "source_type",
    "field_ref",
    "stated_value",
    "interpretation",
    "ground_truth",
    "delta",
    "verifier_status",
    "expected_label",
    "subsets",
    "disease",
]


def load_raw(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{i + 1} JSON 解析失败: {e}") from e
    return rows


def _seed_rng(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - 抽样随机性仅供可复现抽样，非密码用途


def _trace_count_key(row: dict) -> str:
    return str(row.get("trace_id") or "")


class _TraceQuota:
    """跨子集全局 per-trace 配额（单 session ≤ cap 条，含所有子集）。"""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used: Counter = Counter()

    def try_take(self, row: dict) -> bool:
        tk = _trace_count_key(row)
        if self.used[tk] >= self.cap:
            return False
        self.used[tk] += 1
        return True


def _pick_claims(rows: list[dict], n: int, rng: random.Random, quota: _TraceQuota) -> list[dict]:
    """从 rows 中随机抽 n 条，遵守全局 per-trace 配额。"""
    picked: list[dict] = []
    pool = list(rows)
    rng.shuffle(pool)
    for row in pool:
        if len(picked) >= n:
            break
        if quota.try_take(row):
            picked.append(row)
    return picked


def sample_clean(
    rows: list[dict],
    n: int,
    rng: random.Random,
    quota: _TraceQuota,
    excluded: set[int] | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """按 TYPE_TARGETS 分层抽样 clean 子集；类型池不足时其余类型补足。

    Returns:
        (抽样结果, 目标缺口说明 {类型: 原因})
    """
    excluded = excluded or set()
    rows = [r for r in rows if id(r) not in excluded]
    if n <= 0:
        return [], {}
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(str(row["claim"]["claim_type"]), []).append(row)

    chosen: list[dict] = []
    gaps: dict[str, str] = {}
    for t, ratio in TYPE_TARGETS.items():
        take = round(n * ratio)
        sub = by_type.get(t) or []
        picked = _pick_claims(sub, take, rng, quota)
        chosen.extend(picked)
        if len(picked) < take:
            gaps[t] = (
                f"池内仅 {len(sub)} 条（目标 {take}）"
                if sub
                else "池内 0 条（历史报告未产出该类型）"
            )
    # 其余类型 + 类型池不足的回填
    seen_ids = {id(r) for r in chosen}
    others = [r for r in rows if id(r) not in seen_ids]
    fill = _pick_claims(others, n - len(chosen), rng, quota)
    chosen.extend(fill)
    return chosen, gaps


def sample_subset(
    rows: list[dict],
    n: int,
    rng: random.Random,
    quota: _TraceQuota,
    excluded: set[int] | None = None,
) -> list[dict]:
    excluded = excluded or set()
    pool = [r for r in rows if id(r) not in excluded]
    rng.shuffle(pool)
    picked: list[dict] = []
    for row in pool:
        if len(picked) >= n:
            break
        if quota.try_take(row):
            picked.append(row)
    return picked


def is_near_miss(row: dict) -> bool:
    """擦边：gt 可得、delta 相对真值在 (0, 5%] 区间内。"""
    gt, delta = row.get("ground_truth"), row.get("delta")
    if not isinstance(gt, (int, float)) or not isinstance(delta, (int, float)) or gt == 0:
        return False
    return 0 < delta <= NEAR_MISS_REL * abs(float(gt))


def mark_disease(row: dict) -> str | None:
    pre_fix = row.get("trace_version") == "pre_fix"
    return contract_disease(row["claim"], pre_fix=pre_fix)


def _sample_all(
    rows: list[dict], clean_n: int, near_miss_n: int, hedged_n: int, seed: int, cap: int
) -> tuple[list[dict], list[dict], list[dict], dict[str, str]]:
    """给定 cap 做一次完整抽样（对抗子集优先，clean 回填）。"""
    rng = _seed_rng(seed)
    quota = _TraceQuota(cap)
    near_miss = sample_subset([r for r in rows if is_near_miss(r)], near_miss_n, rng, quota)
    hedged = sample_subset(
        [r for r in rows if is_hedged(r["claim"])],
        hedged_n,
        rng,
        quota,
        excluded={id(r) for r in near_miss},
    )
    excluded = {id(r) for r in near_miss} | {id(r) for r in hedged}
    clean, gaps = sample_clean(rows, clean_n, rng, quota, excluded=excluded)
    return clean, near_miss, hedged, gaps


def build(
    input_path: Path,
    clean_n: int,
    near_miss_n: int,
    hedged_n: int,
    seed: int,
    out_prefix: Path,
    max_per_trace: int = MAX_PER_TRACE,
) -> int:
    rows = load_raw(input_path)
    print(f"输入池: {len(rows)} 条 claims")

    # per-trace 配额：默认 8；请求量超出会话容量时自动搜索最小可行 cap 并披露
    n_sessions = len({_trace_count_key(r) for r in rows})
    needed = clean_n + near_miss_n + hedged_n
    cap_floor = max(max_per_trace, -(-needed // n_sessions) if n_sessions else max_per_trace)
    cap_upper = max(Counter(_trace_count_key(r) for r in rows).values()) or max_per_trace
    cap = cap_floor
    clean, near_miss, hedged, gaps = _sample_all(rows, clean_n, near_miss_n, hedged_n, seed, cap)
    while len(clean) + len(near_miss) + len(hedged) < needed and cap < cap_upper:
        cap += 1
        clean, near_miss, hedged, gaps = _sample_all(
            rows, clean_n, near_miss_n, hedged_n, seed, cap
        )
    if cap > max_per_trace:
        print(
            f"[披露] 池仅 {n_sessions} 个 session，{needed} 行考卷按上限 {max_per_trace}/session "
            f"最多 {max_per_trace * n_sessions} 行不足 → per-trace 上限放宽至 {cap}（最小可行）"
        )

    entries: list[dict] = []
    for i, (row, subs) in enumerate(
        [(r, ["clean"]) for r in clean]
        + [(r, ["near_miss"]) for r in near_miss]
        + [(r, ["hedged"]) for r in hedged]
    ):
        disease = mark_disease(row)
        subsets = subs if disease is None else subs + ["regression"]
        entries.append(
            {
                "entry_id": f"benchmark_v1_{i:04d}",
                "claim": row["claim"],
                "ground_truth": row["ground_truth"],
                "delta": row["delta"],
                "verifier_status": row["verifier_status"],
                "rejudged_status": row["rejudged_status"],
                "trace_id": row["trace_id"],
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "trace_timestamp": row["trace_timestamp"],
                "trace_version": row["trace_version"],
                "coverage_gap": row["coverage_gap"],
                "subsets": subsets,
                "disease": disease,
            }
        )

    # 分布披露（验收标准：类型分布 + 单 session 上限 + 目标缺口）
    print("\n== 考卷构成 ==")
    print(
        f"总行数 {len(entries)}（clean {len(clean)} / near-miss {len(near_miss)} / hedged {len(hedged)}）"
    )
    type_counts = Counter(e["claim"]["claim_type"] for e in entries)
    for t, c in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:16s} {c:4d}  {100 * c / len(entries):5.1f}%")
    for t, reason in gaps.items():
        print(f"  [类型缺口] {t}: {reason}")
    per_trace = Counter(e["trace_id"] for e in entries)
    print(f"单一 trace 最多 {max(per_trace.values())} 条（上限 {cap}）")
    print(
        f"regression（契约疾病回归考题）: {sum(1 for e in entries if 'regression' in e['subsets'])} 条"
    )

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_prefix.with_suffix(".jsonl")
    with jsonl_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    csv_path = out_prefix.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            claim = e["claim"]
            w.writerow(
                {
                    "entry_id": e["entry_id"],
                    "stock_code": e["stock_code"],
                    "stock_name": e["stock_name"],
                    "trace_id": e["trace_id"],
                    "trace_timestamp": e["trace_timestamp"],
                    "trace_version": e["trace_version"],
                    "claim_type": claim.get("claim_type"),
                    "source_type": claim.get("source_type"),
                    "field_ref": claim.get("field_ref"),
                    "stated_value": claim.get("stated_value"),
                    "interpretation": claim.get("interpretation"),
                    "ground_truth": e["ground_truth"],
                    "delta": e["delta"],
                    "verifier_status": e["verifier_status"],
                    "expected_label": e["rejudged_status"],
                    "subsets": "+".join(e["subsets"]),
                    "disease": e["disease"] or "",
                }
            )

    # 防锚定版本：删除 verifier_status / expected_label
    labeling_path = out_prefix.parent / f"{out_prefix.name}_for_labeling.csv"
    drop = {"verifier_status", "expected_label"}
    keep = [c for c in _CSV_COLUMNS if c not in drop]
    with labeling_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keep, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            claim = e["claim"]
            w.writerow(
                {
                    "entry_id": e["entry_id"],
                    "stock_code": e["stock_code"],
                    "stock_name": e["stock_name"],
                    "trace_id": e["trace_id"],
                    "trace_timestamp": e["trace_timestamp"],
                    "trace_version": e["trace_version"],
                    "claim_type": claim.get("claim_type"),
                    "source_type": claim.get("source_type"),
                    "field_ref": claim.get("field_ref"),
                    "stated_value": claim.get("stated_value"),
                    "interpretation": claim.get("interpretation"),
                    "ground_truth": e["ground_truth"],
                    "delta": e["delta"],
                    "subsets": "+".join(e["subsets"]),
                    "disease": e["disease"] or "",
                }
            )

    print(f"\n已写: {jsonl_path} / {csv_path} / {labeling_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成校验基准考卷")
    ap.add_argument("--input", required=True, help="claims_raw.jsonl")
    ap.add_argument("--clean", type=int, default=150)
    ap.add_argument("--near-miss", type=int, default=40)
    ap.add_argument("--hedged", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--max-per-trace",
        type=int,
        default=MAX_PER_TRACE,
        help="单 session 上限（池容量不足时自动放宽并披露）",
    )
    ap.add_argument("--out-prefix", required=True, help="输出前缀（jsonl/csv/for_labeling.csv）")
    args = ap.parse_args()
    return build(
        Path(args.input),
        args.clean,
        args.near_miss,
        args.hedged,
        args.seed,
        Path(args.out_prefix),
        max_per_trace=args.max_per_trace,
    )


if __name__ == "__main__":
    sys.exit(main())
