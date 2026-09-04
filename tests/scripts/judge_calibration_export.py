#!/usr/bin/env python
"""judge-人工校准：从 Langfuse 抽样导出标注表（tests/scripts 测试辅助，不进 pytest CI）。

只读约束：仅 GET /api/public/*。输出 JSONL（每行 trace_id/dimension/judge_score/
human_score=null），人工打分回填后由 evals/judge_calibration/measure.py 计算一致性。

用法:
    uv run python -m tests.scripts.judge_calibration_export \
        [--limit 30] [--out tmp/judge-sample.jsonl]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

import requests

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:  # noqa: BLE001, S110
        pass


def export_to_jsonl(out: Path, limit: int) -> list[dict[str, Any]]:
    from evals.judge_calibration.measure import DEFAULT_DIMENSIONS, export_rows

    _load_env()
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/traces",
        params={"limit": min(limit, 100), "page": 1},
        headers={"Authorization": f"Basic {auth}"},
        timeout=40,
    )
    resp.raise_for_status()
    traces = resp.json().get("data") or []

    rows = export_rows(traces, DEFAULT_DIMENSIONS)
    payload = [
        {
            "trace_id": r.trace_id,
            "dimension": r.dimension,
            "judge_score": r.judge_score,
            "human_score": None,
        }
        for r in rows
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for item in payload:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"导出 {len(payload)} 行标注样本 → {out}（人工回填 human_score 后重跑 measure.py）")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="judge-人工校准标注抽样导出")
    parser.add_argument("--limit", type=int, default=30, help="抽样 trace 数（默认 30）")
    parser.add_argument("--out", type=Path, default=Path("tmp/judge-sample.jsonl"))
    args = parser.parse_args()
    export_to_jsonl(args.out, args.limit)


if __name__ == "__main__":
    main()
