#!/usr/bin/env python
"""从 Langfuse 收割历史 citation 校验记录 → claims_raw.jsonl（verifier-baseline-v1 任务 3）。

只读 Langfuse：拉取 deep_analysis trace 的 metadata.citation_report，逐条 claim
落一行记录（claim / verifier_status / ground_truth / delta / trace 元信息 /
trace_version / rejudged_status）。对业务库零写入。

用法:
    uv run python evals/claim_benchmark/harvest.py \
        --from-date 2026-07-01 \
        --out evals/claim_benchmark/data/claims_raw.jsonl

可选: --to-date / --fix-cutoff（契约修复合入时间，trace 晚于此 = post_fix）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.claim_benchmark import rejudge  # noqa: E402
from evals.claim_benchmark._langfuse import (  # noqa: E402
    LangfuseClient,
    _load_env,
    parse_cutoff,
    stock_code_from_trace,
)


def harvest_records(
    client: LangfuseClient,
    from_date: datetime,
    to_date: datetime | None,
    cutoff: datetime,
) -> list[dict]:
    """收割核心：逐 trace 展开 citation_report → claim 记录列表（可单测）。"""
    traces = client.iter_deep_traces(from_date, to_date)
    records: list[dict] = []
    for trace in traces:
        ts = str(trace.get("timestamp") or "")
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        is_post = ts_dt >= cutoff
        stock_name = str((trace.get("name") or "").split(":")[-1])
        stock_code = stock_code_from_trace(trace)
        report = LangfuseClient.extract_report(trace)
        for res in report.get("results") or []:
            claim = res.get("claim") or {}
            gt = res.get("ground_truth")
            delta = res.get("delta")
            records.append(
                {
                    "claim": claim,
                    "verifier_status": res.get("status"),
                    "ground_truth": gt,
                    "delta": delta,
                    "coverage_gap": bool(res.get("coverage_gap")),
                    "trace_id": trace.get("id"),
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "trace_timestamp": ts,
                    "trace_version": "post_fix" if is_post else "pre_fix",
                    "rejudged_status": rejudge.rejudge_claim(claim, gt, delta),
                }
            )
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="收割 Langfuse 历史 citation 校验记录")
    ap.add_argument("--from-date", required=True, help="起始日期（ISO，如 2026-07-01）")
    ap.add_argument("--to-date", default=None, help="截止日期（ISO，可省）")
    ap.add_argument(
        "--fix-cutoff", default=None, help="契约修复合入时间（可省，默认取合入 commit 时间）"
    )
    ap.add_argument("--out", required=True, help="输出 claims_raw.jsonl 路径")
    args = ap.parse_args()

    from_date = (
        datetime.fromisoformat(args.from_date + "T00:00:00")
        if len(args.from_date) <= 10
        else datetime.fromisoformat(args.from_date)
    )
    if from_date.tzinfo is None:
        from_date = from_date.replace(tzinfo=__import__("datetime").timezone.utc)
    to_date = None
    if args.to_date:
        to_date = (
            datetime.fromisoformat(args.to_date + "T00:00:00")
            if len(args.to_date) <= 10
            else datetime.fromisoformat(args.to_date)
        )
        if to_date.tzinfo is None:
            to_date = to_date.replace(tzinfo=__import__("datetime").timezone.utc)
    cutoff = parse_cutoff(args.fix_cutoff)

    _load_env()  # 独立 CLI 运行加载 .env（测试直接构造客户端不走此路径）
    client = LangfuseClient()
    records = harvest_records(client, from_date, to_date, cutoff)
    print("收割 deep_analysis trace: 含 citation_report 的 trace 均已展开")
    print(f"收割 claims: {len(records)} 条")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    versions: dict[str, int] = {}
    for rec in records:
        versions[rec["trace_version"]] = versions.get(rec["trace_version"], 0) + 1
    print(f"已写 {len(records)} 条 claims → {out_path}")
    print(f"trace 版本分布(按 claim 计): {versions}（post_fix 需 >0，否则 --from-date 前移）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
