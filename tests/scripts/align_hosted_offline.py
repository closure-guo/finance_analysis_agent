#!/usr/bin/env python
"""hosted vs 离线 judge 口径对齐（enable-hosted-evaluator spec 1.3）。

对 hosted evaluator 已打分的 trace，从根 span metadata/output 重建 judge 变量
（evals.extract.extract_judge_vars 同口径），用当前离线 rubric 重打四维，
与 hosted 分（source=EVAL）配对算 MAE（阈值 1.0，超限标口径漂移）。

只读约束：仅 GET /api/public/*；离线 judge 分只打印/写 jsonl，不落 Langfuse。

用法:
    uv run python tests/scripts/align_hosted_offline.py \
        [--out reports/hosted-offline-align-20260912.json]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import statistics
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:  # noqa: BLE001, S110
        pass


def _auth() -> str:
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
    return base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()


def _strip_suffix(name: str) -> str:
    return re.sub(r"（.*$", "", name)


def fetch_pairs(auth: str) -> dict[str, dict[str, float]]:
    """按 trace 聚合 hosted（EVAL）与离线（API，维度名精确）分。"""
    hosted: dict[str, dict[str, float]] = {}
    offline: dict[str, dict[str, float]] = {}
    page = 1
    while page <= 40:
        r = requests.get(
            f"{LANGFUSE_HOST}/api/public/scores",
            params={"limit": 100, "page": page},
            headers={"Authorization": f"Basic {auth}"},
            timeout=40,
        )
        rows = r.json().get("data") or []
        if not rows:
            break
        for s in rows:
            v = s.get("value")
            if not isinstance(v, (int, float)):
                continue
            tid = str(s.get("traceId") or "")
            name = str(s.get("name") or "")
            if s.get("source") == "EVAL":
                hosted.setdefault(tid, {})[_strip_suffix(name)] = float(v)
            elif s.get("source") == "API":
                offline.setdefault(tid, {})[name] = float(v)
        tp = ((r.json().get("meta") or {}).get("totalPages")) or 1
        if page >= tp:
            break
        page += 1
    return hosted, offline


def rebuild_state(trace: dict, root_meta: dict, root_out: dict) -> dict:
    """从 deep_analysis 根 span 重建 extract_judge_vars 所需的 state 子集。"""
    return {
        "final_report": root_meta.get("report_markdown") or "",
        "focus_summary": root_out.get("final_report_summary") or "",
        "analyst_reports": root_meta.get("analyst_reports") or {},
        "debate_history": root_meta.get("debate_history") or [],
        "research_manager_conclusion": root_meta.get("research_manager_decision") or "",
        "risk_judgment": root_meta.get("risk_judgment") or {},
        "risk_metrics": root_meta.get("risk_metrics") or {},
        "risk_debate_history": root_meta.get("risk_debate_history") or [],
        "final_trade_decision": root_out.get("final_trade_decision") or "",
        "fund_manager_decision": root_out.get("fund_manager_decision") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="hosted vs 离线 judge 口径对齐")
    parser.add_argument("--out", type=Path, default=Path("reports/hosted-offline-align.json"))
    args = parser.parse_args()

    _load_env()
    auth = _auth()
    hosted, offline = fetch_pairs(auth)

    from evals.extract import extract_judge_vars
    from evals.judges import run_judge

    dims = ["report_relevance", "debate_quality", "decision_grounding", "consistency"]
    results: list[dict] = []
    for tid, hscores in sorted(hosted.items()):
        if not hscores:
            continue
        trace = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces/{tid}",
            headers={"Authorization": f"Basic {auth}"},
            timeout=40,
        ).json()
        obs = (
            requests.get(
                f"{LANGFUSE_HOST}/api/public/observations",
                params={"traceId": tid, "limit": 100},
                headers={"Authorization": f"Basic {auth}"},
                timeout=40,
            )
            .json()
            .get("data")
            or []
        )
        roots = [o for o in obs if str(o.get("name", "")).startswith("deep_analysis")]
        if not roots:
            print(
                f"[skip] {tid[:8]} 无 deep_analysis 根 span（experiment-item trace 无法重建 state）"
            )
            continue
        root = roots[0]
        state = rebuild_state(trace, root.get("metadata") or {}, root.get("output") or {})
        query = ""
        tin = trace.get("input")
        if isinstance(tin, dict):
            query = str(tin.get("query") or "")
        elif isinstance(tin, str):
            query = tin
        vars_ = extract_judge_vars(state, query=query)
        for dim, hosted_val in sorted(hscores.items()):
            if dim not in dims:
                continue
            res = run_judge(dim, vars_)
            results.append(
                {
                    "trace_id": tid,
                    "dimension": dim,
                    "hosted": hosted_val,
                    "offline": res.get("score"),
                    "offline_reason": str(res.get("reason", ""))[:100],
                }
            )
            print(f"{tid[:8]} {dim:20s} hosted={hosted_val} offline={res.get('score')}")

    paired = [r for r in results if r["offline"] is not None]
    mae = (
        round(statistics.mean(abs(r["hosted"] - r["offline"]) for r in paired), 4)
        if paired
        else None
    )
    summary = {
        "mae": mae,
        "drift": bool(mae is not None and mae > 1.0),
        "pairs": len(paired),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MAE={mae} pairs={len(paired)} drift={summary['drift']} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
