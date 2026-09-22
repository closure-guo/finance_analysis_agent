#!/usr/bin/env python
"""report_relevance rubric v4 离线重判：round7 同批材料，验「5 分档锚点判例」。

背景（delta resolve-report-relevance-zero-variance）：该维在 r3–r9 零方差（全 5，
Spearman 不可算）；quick 段已停评，deep 段保留并以 v4 锚点收紧 5 分档（查询的
显式子问题须逐一回答）。本脚本按「同材料仅换 rubric」的纯归因法离线重判
round7 的 14 条 report_relevance 盲标行，与人工分对照：MAE ≤ 1.0 且方向一致率
（>3 分界）≥ 0.8 达标方可上线（Judge 校准门禁契约）。

只读：dry-run 默认，不写 Langfuse score。

用法:
    uv run python tests/scripts/rejudge_relevance_v4.py \
        --blind evals/judge_calibration/data/judge-sample-round7-blind-v2.xlsx \
        --judge-v3 evals/judge_calibration/data/judge-sample-round7-judge.jsonl \
        --out evals/judge_calibration/data/judge-sample-round12-relevance-v4.jsonl
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import openpyxl  # noqa: E402
import requests  # noqa: E402

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")


def _auth() -> str:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (pk and sk):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()


def load_blind(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    return [
        {"trace_id": str(r[0]), "dimension": str(r[1]), "human": float(r[2])}
        for r in ws.iter_rows(min_row=2, values_only=True)
        if r[2] is not None and r[1] == "report_relevance"
    ]


def load_v3(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("dimension") == "report_relevance":
            out[str(row["trace_id"])] = float(row["judge_score"])
    return out


def fetch_vars(trace_id: str, auth: str) -> dict[str, str] | None:
    """从 Langfuse 观测拉 round7 渲染 prompt，反解 {query, report}。"""
    from evals.judge_calibration.material import (
        detect_dimension,
        extract_sections,
        prompt_from_observation_input,
    )

    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/observations",
        params={"traceId": trace_id, "limit": 100},
        headers={"Authorization": f"Basic {auth}"},
        timeout=30,
    )
    resp.raise_for_status()
    for o in resp.json().get("data") or []:
        if str(o.get("name") or "") != "judge":
            continue
        prompt = prompt_from_observation_input(o.get("input"))
        if prompt and detect_dimension(prompt) == "report_relevance":
            sections = extract_sections(prompt, "report_relevance")
            return {
                "query": sections.get("【用户查询】", ""),
                "report": sections.get("【分析报告】", ""),
            }
    return None


def main() -> int:
    from dotenv import load_dotenv
    from evals.judges import RUBRIC_VERSIONS, run_judge_mean

    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind", type=Path, required=True)
    ap.add_argument("--judge-v3", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--judge-repeats", type=int, default=3)
    args = ap.parse_args()
    assert RUBRIC_VERSIONS["report_relevance"] == 4, "重判须在 v4 rubric 下执行"

    rows = load_blind(args.blind)
    v3 = load_v3(args.judge_v3)
    auth = _auth()
    print(f"relevance v4 重判 {len(rows)} 条（K={args.judge_repeats} 均值，材料同 round7）")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done: dict[str, dict] = {}
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["trace_id"]] = row

    for row in rows:
        tid = row["trace_id"]
        if tid in done:
            print(f"  [skip] {tid[:8]} 已完成（断点续判）")
            continue
        variables = fetch_vars(tid, auth)
        if not variables or not variables["query"]:
            print(f"  [miss] {tid[:8]} 取材失败，跳过（不计入一致性）")
            continue
        result = run_judge_mean("report_relevance", variables, repeats=args.judge_repeats)
        out_row = {
            "trace_id": tid,
            "human": row["human"],
            "v3": v3.get(tid),
            "v4": result.get("score"),
            "scores": result.get("scores"),
            "reason": result.get("reason"),
        }
        done[tid] = out_row
        with args.out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
        print(f"  {tid[:8]} human={row['human']} v3={v3.get(tid)} v4={out_row['v4']}")

    paired = [r for r in done.values() if r["v4"] is not None]
    if not paired:
        print("无有效配对行")
        return 1
    mae = sum(abs(r["v4"] - r["human"]) for r in paired) / len(paired)
    direction = sum(1 for r in paired if (r["v4"] > 3) == (r["human"] > 3)) / len(paired)
    v4_mean = sum(r["v4"] for r in paired) / len(paired)
    print(
        f"\n[summary] n={len(paired)} MAE={mae:.3f} 方向一致率={direction:.3f} "
        f"v4均值={v4_mean:.2f}（v3 批次均值≈5.0）｜达标判据：MAE≤1.0 且 方向≥0.80"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
