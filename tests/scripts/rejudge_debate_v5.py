#!/usr/bin/env python
"""debate_quality rubric v5 离线重判：对 round9 既有 trace 用 v5 强制枚举 rubric 重评。

背景（2026-09-14 round9 审计）：v4 判例在 4 分档生效，但 5 分档对论点标头的
纯定性表述视而不见——宁德/美的/平安银行三行标头含纯定性论点仍被给满分。
v5 加强制枚举动作（评分前逐条标注论点标头，任一纯定性即封顶 4）。

做法（不重跑 pipeline，零业务写入，纯归因：同一批辩论内容只有 rubric 变）：
1. 从 round9 trace 映射取 9 条 deep trace；
2. 逐条拉 debate_quality judge 观测 input，extract_sections 反解 debate_history；
3. 用当前（v5）rubric run_judge 重评；
4. 对比 Langfuse 落库的 v4 分 vs v5 新分，输出 jsonl。

只读：默认 dry-run 只打印；--write 才 POST 新 score（name=debate_quality，
comment 前缀 [rubric-v5]）。

用法:
    uv run python tests/scripts/rejudge_debate_v5.py \
        --trace-map tmp/round9-trace-map.json \
        --v4-scores tmp/round9-judge-reasons.json \
        --out evals/judge_calibration/data/judge-sample-round10-debate-v5.jsonl \
        [--write]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:  # noqa: BLE001, S110
        pass


def _auth() -> str:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (pk and sk):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()


def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-map", required=True)
    ap.add_argument("--v4-scores", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    from evals.judge_calibration.material import (
        detect_dimension,
        extract_sections,
        prompt_from_observation_input,
    )
    from evals.judges import RUBRIC_VERSIONS, run_judge

    auth = _auth()
    trace_map = json.loads(Path(args.trace_map).read_text(encoding="utf-8"))
    v4 = json.loads(Path(args.v4_scores).read_text(encoding="utf-8"))
    # deep 集合 = v4 分数文件里有 debate_quality 的 trace（该文件只含 deep trace 的
    # debate/dg/consistency 三维，天然排除 quick）——不用 query 前缀过滤（会漏
    # 「贵州茅台的现金流健康吗」这类非「全面分析」开头的 deep 查询）
    deep = {tid: trace_map.get(tid, "") for tid in v4 if "debate_quality" in v4[tid]}
    print(
        f"debate rubric v{RUBRIC_VERSIONS['debate_quality']} 重判 {len(deep)} 条 round9 deep trace"
    )

    rows = []
    for tid, query in sorted(deep.items()):
        resp = requests.get(
            f"{LANGFUSE_HOST}/api/public/observations",
            params={"traceId": tid, "limit": 100},
            headers={"Authorization": f"Basic {auth}"},
            timeout=30,
        )
        resp.raise_for_status()
        debate_text = ""
        for o in resp.json().get("data") or []:
            if str(o.get("name") or "") != "judge":
                continue
            prompt = prompt_from_observation_input(o.get("input"))
            if prompt and detect_dimension(prompt) == "debate_quality":
                debate_text = extract_sections(prompt, "debate_quality").get("【多空辩论记录】", "")
                break
        if not debate_text:
            print(f"  [skip] {tid[:8]} 无 debate 材料")
            continue
        result = run_judge("debate_quality", {"debate_history": debate_text})
        v5_score = result.get("score")
        v4_score = (v4.get(tid, {}).get("debate_quality") or [None])[0]
        reason = (result.get("reason") or "")[:200]
        rows.append(
            {
                "trace_id": tid,
                "query": query,
                "dimension": "debate_quality",
                "v4_score": v4_score,
                "v5_score": v5_score,
                "v5_reason": reason,
            }
        )
        flag = "↓" if (v4_score or 0) > (v5_score or 0) else ("=" if v4_score == v5_score else "?")
        print(f"  {tid[:8]} {query[:18]:<18} v4={v4_score} → v5={v5_score} {flag}  {reason[:60]}")

        if args.write and v5_score is not None:
            requests.post(
                f"{LANGFUSE_HOST}/api/public/scores",
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                json={
                    "traceId": tid,
                    "name": "debate_quality",
                    "value": float(v5_score),
                    "comment": f"[rubric-v5] {reason}",
                    "dataType": "NUMERIC",
                },
                timeout=30,
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    drops = [r for r in rows if (r["v4_score"] or 0) > (r["v5_score"] or 0)]
    fives_v4 = [r for r in rows if r["v4_score"] == 5]
    fives_v5 = [r for r in rows if r["v5_score"] == 5]
    print(f"\n→ {out}")
    print(
        f"v4 满分 {len(fives_v5) and len(fives_v4)} 行 → v5 满分 {len(fives_v5)} 行；降分 {len(drops)} 行"
    )
    for r in drops:
        print(f"  {r['trace_id'][:8]} {r['query'][:18]} {r['v4_score']}→{r['v5_score']}")


if __name__ == "__main__":
    main()
