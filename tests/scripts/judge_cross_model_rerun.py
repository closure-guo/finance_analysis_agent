#!/usr/bin/env python
"""judge 跨模型一致性重评：用另一家 LLM 重跑 judge 标注样本的全部 (trace, 维度)，
与原 judge 算 Spearman / MAE / 方向一致率（复用 evals/judge_calibration/measure.py）。

默认交叉模型：opencode zen/go 网关的 qwen3.8-flash（与原始 judge deepseek-v4-flash
同网关、不同模型家族）。LLM↔LLM 一致率是 rubric 脆弱性的**代理门禁**（对应 spec
3.1 阈值机制），**不等于**人工校准（spec 3.3 人工标注仍开放）——报告标题明确标注
cross-model proxy，不得冒充人工校准结论。

用法:
    uv run python tests/scripts/judge_cross_model_rerun.py [--sample PATH] [--model x]
        [--limit N] [--out PATH]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
DEFAULT_MODEL = "openai/qwen3.8-flash"


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def _fetch_judge_vars(trace_id: str) -> dict[str, Any]:
    """取 trace 的 output.judge_vars（judge 打分所见输入，API 只读）。"""
    public_key = os.environ["LANGFUSE_PUBLIC_KEY"]
    secret_key = os.environ["LANGFUSE_SECRET_KEY"]
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    import requests

    resp = requests.get(
        f"{LANGFUSE_HOST}/api/public/traces/{trace_id}",
        headers={"Authorization": f"Basic {auth}"},
        timeout=40,
    )
    resp.raise_for_status()
    return (resp.json().get("output") or {}).get("judge_vars") or {}


def _cross_judge(
    dimension: str, variables: dict[str, Any], cross_model: str, session: str
) -> dict[str, Any]:
    """用 cross_model 直连 opencode zen/go 重评（绕过 broken 的生产 gateway：网关
    现在要求 x-opencode-session 头，complete_text 不发 → 全部 400；见 incident 待报）。
    复刻 run_judge 语义：input_missing 短路 / 解析失败重试一次 / score 1-5 越界即败。
    """
    from evals.judges import _DIMENSION_REQUIRED_VARS, _render
    from litellm import completion

    from finance_agent.nodes._llm_utils import parse_json_response

    required = tuple(_DIMENSION_REQUIRED_VARS.get(dimension, ()))
    missing = [k for k in required if not variables.get(k)]
    if missing:
        return {"score": None, "reason": f"input_missing:{','.join(missing)}"}
    prompt = _render(dimension, variables)
    base_url = os.environ.get("CROSS_BASE_URL") or os.environ["JUDGE_BASE_URL"]
    api_key = os.environ.get("CROSS_API_KEY") or os.environ["JUDGE_API_KEY"]
    headers = {"x-opencode-session": session} if "opencode.ai" in base_url else {}
    # 温度策略：多数端点收 temperature=0（复现优先）；k3-256k 等只允许 temperature=1，
    # 第一轮带温度被拒后第二轮不带温度重试（解析失败同样落到第二轮）。
    for _attempt in range(2):
        try:
            call_kwargs: dict[str, Any] = {
                "model": cross_model,
                "messages": [{"role": "user", "content": prompt}],
                "api_base": base_url,
                "api_key": api_key,
            }
            if _attempt == 0:
                call_kwargs["temperature"] = 0.0
            if headers:
                call_kwargs["extra_headers"] = headers
            resp = completion(**call_kwargs)
            text = str(resp.choices[0].message.content or "")
            data = parse_json_response(text)
            score = int(data["score"])
            if not 1 <= score <= 5:
                raise ValueError(f"score 越界: {score}")
            return {"score": score, "reason": str(data.get("reason", ""))}
        except Exception:  # noqa: S112 — 温度拒绝/解析失败均落到下一轮或 parse_failed
            continue
    return {"score": None, "reason": "judge_parse_failed"}


def run_cross(trace_id: str, dimension: str, cross_model: str) -> dict[str, Any] | None:
    """用 cross_model 重跑某维度 judge；失败返回 None（调用方跳过不阻塞）。"""
    try:
        vars_ = _fetch_judge_vars(trace_id)
        if not vars_:
            return {"trace_id": trace_id, "dimension": dimension, "error": "judge_vars_missing"}
        result = _cross_judge(dimension, vars_, cross_model, session=f"judge-cross-{trace_id}")
        return {
            "trace_id": trace_id,
            "dimension": dimension,
            "cross_score": result.get("score"),
            "cross_reason": result.get("reason", ""),
        }
    except Exception as e:  # noqa: BLE001 — 单条失败不阻塞整批
        return {"trace_id": trace_id, "dimension": dimension, "error": f"{type(e).__name__}: {e}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="judge 跨模型一致性重评（代理门禁）")
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("evals/judge_calibration/data/judge-sample-round1.jsonl"),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"交叉模型（默认 {DEFAULT_MODEL}）")
    parser.add_argument("--limit", type=int, default=0, help="限制处理条数（0=全部，冒烟用）")
    parser.add_argument(
        "--batch", type=int, default=0, help="本批最多处理条数（0=不限；配合续跑分批）"
    )
    parser.add_argument("--dim", action="append", help="只处理指定维度（可多次；缺省=全部维度）")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/judge_calibration/data/judge-sample-round1-cross.jsonl"),
    )
    args = parser.parse_args()
    _load_env()

    rows = [
        json.loads(line)
        for line in args.sample.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # 保证跨模型一致使用同一份原始 judge_score
    original: dict[tuple[str, str], float] = {
        (r["trace_id"], r["dimension"]): float(r["judge_score"]) for r in rows
    }
    pairs = sorted({(r["trace_id"], r["dimension"]) for r in rows})
    if args.dim:
        pairs = [p for p in pairs if p[1] in args.dim]

    # 续跑语义：读已有输出，跳过已评 (trace, dim)；batch 限本批量（分多批跑完，避免
    # 单命令超时；重定向时 stdout 块缓冲，print 显式 flush 便于观察进度）。
    done: dict[tuple[str, str], dict[str, Any]] = {}
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                done[(d["trace_id"], d["dimension"])] = d
    pending = [p for p in pairs if p not in done]
    if args.limit:
        pending = pending[: args.limit]
    if args.batch:
        pending = pending[: args.batch]
    print(f"已评 {len(done)} 对，本批待评 {len(pending)} 对，交叉模型 {args.model}", flush=True)

    for i, (tid, dim) in enumerate(pending, 1):
        res = run_cross(tid, dim, args.model)
        if not res or res.get("error"):
            print(
                f"  [{i}/{len(pending)}] {tid[:8]} {dim} 失败: {res.get('error') if res else '?'}",
                flush=True,
            )
            continue
        done[(tid, dim)] = {
            "trace_id": tid,
            "dimension": dim,
            "judge_score": original[(tid, dim)],
            "cross_score": res["cross_score"],
            "cross_reason": res.get("cross_reason", ""),
            "human_score": None,
        }
        # 每条完成即落盘（超时/中断不丢进度；结尾再全量重写一次收敛）
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for tid2, dim2 in pairs:
                row2 = done.get((tid2, dim2))
                if row2:
                    fh.write(json.dumps(row2, ensure_ascii=False) + "\n")
        if i % 10 == 0:
            print(f" 已重评 {i}/{len(pending)}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for tid, dim in pairs:
            row = done.get((tid, dim))
            if row:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"完成：累计成功 {len(done)}/{len(pairs)} → {args.out}", flush=True)


if __name__ == "__main__":
    main()
