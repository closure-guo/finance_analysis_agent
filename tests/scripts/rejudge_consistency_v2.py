#!/usr/bin/env python
"""consistency rubric v2 重评：对既有 trace 用新 rubric 重新调 judge。

背景（2026-09-09 round5 校准实测）：consistency v1 rubric 未定义 approve 的
批准对象，judge 把「Risk watch + FM approve（批准观望）」系统性误判为冲突
（11 条中 7 条打 1-3 分）。v2 rubric 显式定义语义后需对同批 trace 重评。

做法（不重跑 pipeline，零业务写入）：
1. 从 Langfuse 取每条 trace 落库的旧 rubric 渲染 prompt（judge 观测 input）；
2. 按【小节】标记反解出 5 个变量值（模板可逆，已验证）；
3. 用 v2 rubric 重渲染 → run_judge（新分落 Langfuse score）；
4. 输出新 judge 分 jsonl（measure.py --judge-jsonl 合并用）。

只读约束：业务侧仅 run_judge 产出的 judge score（make_evaluation 由调用方
决定是否落库——本脚本直接 POST /api/public/scores 需显式 --write 开关，
默认 dry-run 只打印）。

用法:
    uv run python tests/scripts/rejudge_consistency_v2.py \
        --traces evals/judge_calibration/data/judge-sample-round5.jsonl \
        --out evals/judge_calibration/data/judge-sample-round5-judge-v2-rubric.jsonl \
        [--write]  # 落库新 score（name=consistency，comment 前缀 [rubric-v2]）
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
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
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
    return base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()


_MARKER_VAR_RE = re.compile(r"(【[^】]+】)\{\{(\w+)\}\}")


def _fetch_judge_prompt(trace_id: str, auth: str) -> str | None:
    """取该 trace 落库的 consistency judge 渲染 prompt（无则 None）。"""
    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/traces/{trace_id}",
        headers={"Authorization": f"Basic {auth}"},
        timeout=40,
    )
    resp.raise_for_status()
    for o in resp.json().get("observations") or []:
        if str(o.get("name")) != "judge":
            continue
        from evals.judge_calibration.material import prompt_from_observation_input

        prompt = prompt_from_observation_input(o.get("input"))
        if prompt and "一致性评审专家" in prompt:
            return prompt
    return None


def _extract_variables(prompt: str) -> dict[str, str] | None:
    """从旧 prompt 按【小节】标记反解变量（v1/v2 小节集合一致，可逆）。"""
    from evals.judge_calibration.material import _TAIL_ANCHORS, extract_sections

    # 尾部锚点前截断，避免 rubric 指令混进末节变量值
    hits = [prompt.find(a, len("【")) for a in _TAIL_ANCHORS]
    hits = [h for h in hits if h > 0]
    body = prompt[: min(hits)] if hits else prompt

    marker_to_var = _MARKER_VAR_RE.findall(
        __import__("evals.judges", fromlist=["RUBRICS"]).RUBRICS["consistency"]
    )
    sections = extract_sections(prompt, "consistency")
    variables: dict[str, str] = {}
    for marker, var in marker_to_var:
        # extract_sections 返回的是 _clean 压缩空白后的文本；重渲染前须还原原始段
        i = body.find(marker)
        if i < 0:
            return None
        start = i + len(marker)
        nxt = [body.find(m, start) for m, _ in marker_to_var]
        nxt = [n for n in nxt if n >= 0]
        end = min(nxt) if nxt else len(body)
        variables[var] = body[start:end].strip()
    return variables


def main() -> int:
    parser = argparse.ArgumentParser(description="consistency rubric v2 重评")
    parser.add_argument(
        "--traces", type=Path, required=True, help="标注样本 jsonl（含 trace_id/dimension）"
    )
    parser.add_argument("--out", type=Path, required=True, help="新 judge 分 jsonl 输出")
    parser.add_argument(
        "--write", action="store_true", help="新分落库 Langfuse score（默认 dry-run）"
    )
    args = parser.parse_args()

    _load_env()
    auth = _auth()

    from evals.judges import RUBRIC_VERSIONS, run_judge

    rows = [json.loads(line) for line in args.traces.open(encoding="utf-8")]
    targets = [r for r in rows if r.get("dimension") == "consistency"]
    print(f"consistency 待重评 {len(targets)} 条 | rubric v{RUBRIC_VERSIONS['consistency']}")

    results: list[dict] = []
    for r in targets:
        tid = r["trace_id"]
        prompt = _fetch_judge_prompt(tid, auth)
        if not prompt:
            print(f"[skip] {tid[:8]} 无落库 consistency prompt")
            continue
        variables = _extract_variables(prompt)
        if not variables:
            print(f"[skip] {tid[:8]} 变量反解失败")
            continue
        result = run_judge("consistency", variables)
        old = r.get("judge_score")
        print(f"{tid[:8]} 旧分={old} 新分={result['score']} ({result.get('reason', '')[:60]})")
        results.append(
            {
                "trace_id": tid,
                "dimension": "consistency",
                "judge_score": result["score"],
                "judge_reason": result.get("reason", ""),
                "rubric_version": RUBRIC_VERSIONS["consistency"],
                "prev_judge_score": old,
            }
        )
        if args.write and result["score"] is not None:
            requests.post(
                f"{LANGFUSE_HOST}/api/public/scores",
                headers={"Authorization": f"Basic {auth}"},
                json={
                    "traceId": tid,
                    "name": "consistency",
                    "value": result["score"],
                    "comment": f"[rubric-v2] {result.get('reason', '')}",
                    "dataType": "NUMERIC",
                },
                timeout=30,
            ).raise_for_status()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for item in results:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"→ {args.out}（{len(results)} 条；--write={'已落库' if args.write else '未落库'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
