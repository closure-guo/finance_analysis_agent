#!/usr/bin/env python
"""judge-人工校准：从 Langfuse 抽样导出标注表（tests/scripts 测试辅助，不进 pytest CI）。

只读约束：仅 GET /api/public/*。输出 JSONL（每行 trace_id/dimension/judge_score/
human_score=null），人工打分回填后由 evals/judge_calibration/measure.py 计算一致性。

用法:
    uv run python tests/scripts/judge_calibration_export.py \
        [--limit 30] [--out tmp/judge-sample.jsonl]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:  # noqa: BLE001, S110
        pass


def export_to_jsonl(out: Path, limit: int) -> list[dict[str, Any]]:
    from evals.judge_calibration.measure import DEFAULT_DIMENSIONS

    _load_env()
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

    # 从 scores 端点按维度名聚合（离线 judge 的 make_evaluation 落点：name 精确等于
    # 维度名，comment 为该轮 reason）。不走 traces+observations 逐条 enrichment——
    # 全库 727 条 score 只 ~140 行命中 4 维度，按 trace 翻页会超时（实测 240s 未完成）。
    # hosted evaluator 的分数名带中文后缀（如 report_relevance（报告切题度）），
    # 精确匹配天然排除——校准对象是离线 rubric。采样凑够 limit 条 trace 或翻完为止。
    dims = set(DEFAULT_DIMENSIONS)
    per_trace: dict[str, dict[str, float]] = {}
    reasons: dict[tuple[str, str], str] = {}
    page = 1
    while len(per_trace) < limit and page <= 30:
        resp = requests.get(
            f"{LANGFUSE_HOST}/api/public/scores",
            params={"limit": 100, "page": page},
            headers={"Authorization": f"Basic {auth}"},
            timeout=40,
        )
        resp.raise_for_status()
        entries = resp.json().get("data") or []
        if not entries:
            break
        for s in entries:
            name = str(s.get("name") or "")
            if name not in dims:
                continue
            value = s.get("value")
            if not isinstance(value, (int, float)):
                continue
            trace_id = str(s.get("traceId") or "")
            if not trace_id:
                continue
            per_trace.setdefault(trace_id, {})[name] = float(value)
            reason = str(s.get("comment") or "")
            if reason:
                reasons[(trace_id, name)] = reason
        page += 1

    payload = [
        {
            "trace_id": tid,
            "trace_url": f"{LANGFUSE_HOST}/trace/{tid}",
            "dimension": dim,
            "judge_score": score,
            "judge_reason": reasons.get((tid, dim), ""),
            "human_score": None,
        }
        for tid, scores in sorted(per_trace.items())[:limit]
        for dim, score in sorted(scores.items())
    ]
    if not payload:
        print(
            "未找到带 judge 评分的 trace：先跑 evals/run.py 出实验数据（scores 端点按 4 维度名精确聚合）"
        )
        return payload
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for item in payload:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(
        f"导出 {len(payload)} 行标注样本（{len({p['trace_id'] for p in payload})} trace）→ {out}（人工回填 human_score 后重跑 measure.py）"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="judge-人工校准标注抽样导出")
    parser.add_argument("--limit", type=int, default=30, help="抽样 trace 数（默认 30）")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/judge_calibration/data/judge-sample-round1.jsonl"),
        help="标注 JSONL 输出路径（每行含 trace_url 直达 Langfuse；人工回填 human_score 后跑 measure.py）",
    )
    args = parser.parse_args()
    export_to_jsonl(args.out, args.limit)


if __name__ == "__main__":
    main()
