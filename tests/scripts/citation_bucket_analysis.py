#!/usr/bin/env python
"""存量 trace 分析：claim 校验 FAIL 分桶 + D6 打回解决率（不花 LLM 余额，只读 Langfuse）。

回答两个问题：
1. citation_pass 偏低的 FAIL 分桶分布（issue #105 欠账）——value_mismatch /
   path_unresolvable / semantic_* / internal_inconsistency 各占多少；
2. D6 打回补 claim 回路的量化——citation_coverage 分数 metadata 里的 unmatched
   在最终落盘的 trace 上还剩多少、有多少 trace 带着 coverage gap 结束。

用法:
    uv run python tests/scripts/citation_bucket_analysis.py [--from-date 2026-08-01]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.claim_benchmark._langfuse import LangfuseClient, _load_env  # noqa: E402


def fetch_coverage_score(client: LangfuseClient, trace_id: str) -> dict | None:
    """拉单条 trace 的 citation_coverage score（traces 列表 API 不内联 scores）。"""
    import requests

    r = requests.get(
        f"{client.host}/api/public/scores",
        params={"traceId": trace_id, "limit": 50},
        auth=client.auth,
        timeout=30,
    )
    r.raise_for_status()
    for s in r.json().get("data") or []:
        if s.get("name") == "citation_coverage":
            return s
    return None


def analyze(traces: list[dict], client: LangfuseClient) -> dict:
    fail_buckets: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    per_trace_fail: list[dict] = []
    coverage_gaps: list[dict] = []

    for t in traces:
        md = t.get("metadata") or {}
        report = md.get("citation_report") or {}
        results = report.get("results") or []
        trace_fail: Counter[str] = Counter()
        for r in results:
            status = str(r.get("status") or "UNKNOWN")
            status_counts[status] += 1
            if status == "FAIL":
                bucket = str(r.get("bucket") or "unbucketed")
                fail_buckets[bucket] += 1
                trace_fail[bucket] += 1
        if trace_fail:
            per_trace_fail.append(
                {
                    "trace_id": t.get("id"),
                    "name": t.get("name"),
                    "timestamp": t.get("timestamp"),
                    "fail_buckets": dict(trace_fail),
                    "iteration_count": md.get("iteration_count"),
                }
            )
        # D6：citation_coverage score 的 metadata.unmatched 是最终一轮仍无人认领的数字
        s = fetch_coverage_score(client, str(t.get("id")))
        if s:
            smd = s.get("metadata") or {}
            if isinstance(smd, str):
                try:
                    smd = json.loads(smd)
                except json.JSONDecodeError:
                    smd = {}
            unmatched = smd.get("unmatched") or []
            if unmatched:
                coverage_gaps.append(
                    {
                        "trace_id": t.get("id"),
                        "name": t.get("name"),
                        "timestamp": t.get("timestamp"),
                        "coverage": s.get("value"),
                        "unmatched_count": len(unmatched),
                        "unmatched_sample": unmatched[:5],
                    }
                )

    total_fail = sum(fail_buckets.values())
    # surgical-citation-repair（4.3 口径）：trace metadata 的 surgical_repairs 遥测
    repaired_total = 0
    repaired_traces = 0
    for t in traces:
        md = t.get("metadata") or {}
        n = md.get("value_mismatch_repaired") or 0
        if n:
            repaired_traces += 1
            repaired_total += int(n)
        elif md.get("surgical_repairs"):
            # 旧埋点形态：仅 surgical_repairs 明细（不含已修复计数）——按明细条数计
            repaired_traces += 1
            repaired_total += len(md["surgical_repairs"])
    return {
        "trace_count": len(traces),
        "claim_status": dict(status_counts),
        "fail_total": total_fail,
        "fail_bucket_distribution": {
            b: {"count": c, "share": round(c / total_fail, 4) if total_fail else 0.0}
            for b, c in fail_buckets.most_common()
        },
        "traces_with_fail": len(per_trace_fail),
        "per_trace_fail": per_trace_fail,
        "d6_coverage": {
            "traces_with_residual_unmatched": len(coverage_gaps),
            "residual_unmatched_total": sum(g["unmatched_count"] for g in coverage_gaps),
            "detail": coverage_gaps,
        },
        "surgical_repair": {
            "traces_with_repaired": repaired_traces,
            "value_mismatch_repaired_total": repaired_total,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2026-08-01")
    parser.add_argument("--out", default="reports/citation-bucket-analysis.json")
    args = parser.parse_args()

    _load_env()
    client = LangfuseClient()
    from_date = datetime.fromisoformat(args.from_date).replace(tzinfo=UTC)
    traces = client.iter_deep_traces(from_date)
    print(f"拉取到 {len(traces)} 条 deep_analysis trace（{args.from_date} 起）")

    result = analyze(traces, client)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"claim 状态分布: {result['claim_status']}")
    print(f"FAIL 共 {result['fail_total']} 条，分桶:")
    for b, d in result["fail_bucket_distribution"].items():
        print(f"  {b}: {d['count']} ({d['share']:.1%})")
    d6 = result["d6_coverage"]
    print(
        f"D6: {d6['traces_with_residual_unmatched']} 条 trace 结束时仍有 unmatched，"
        f"残留共 {d6['residual_unmatched_total']} 个数字"
    )
    print(f"明细已写入 {out}")


if __name__ == "__main__":
    main()
