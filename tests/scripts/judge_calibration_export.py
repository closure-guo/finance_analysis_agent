#!/usr/bin/env python
"""judge-人工校准：从 Langfuse 抽样导出标注表（tests/scripts 测试辅助，不进 pytest CI）。

只读约束：仅 GET /api/public/*。默认输出 JSONL（每行 trace_id/dimension/judge_score/
human_score=null），人工打分回填后由 evals/judge_calibration/measure.py 计算一致性。

--csv 模式（标注体验优化）：额外产出 CSV 标注表——每行含 material_summary 列
（从该 trace 的 judge generation 输入 prompt 按维度切出的关键材料摘要，标注人
离线可判，无需逐条开 Langfuse），并产出同名 .rubrics.md 伴读文件（四维度 rubric
速查 + 指标速查）。摘要拉取失败/缺失时该行 material_summary 为空，标注人点
trace_url 查看。

用法:
    uv run python tests/scripts/judge_calibration_export.py \
        [--limit 30] [--out tmp/judge-sample.jsonl] [--csv tmp/judge-sample.csv]
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


def _auth() -> str:
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        raise RuntimeError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置")
    return base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()


def export_to_jsonl(out: Path, limit: int) -> list[dict[str, Any]]:
    from evals.judge_calibration.measure import DEFAULT_DIMENSIONS

    _load_env()
    auth = _auth()

    # Langfuse v3 的 trace 直链是 /project/{projectId}/traces/{traceId}（/trace/<id>
    # 会报 "not have access"）。projectId 从 /api/public/projects 取（该 key 的首个项目）。
    projects = (
        requests.get(
            f"{LANGFUSE_HOST}/api/public/projects",
            headers={"Authorization": f"Basic {auth}"},
            timeout=30,
        )
        .json()
        .get("data")
        or []
    )
    project_id = str(projects[0]["id"]) if projects else ""

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
            "trace_url": f"{LANGFUSE_HOST}/project/{project_id}/traces/{tid}",
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


def _fetch_judge_summaries(trace_ids: list[str], auth: str) -> dict[str, dict[str, str]]:
    """定点拉每条 trace 的 observations，从 judge generation 输入切出各维度人审摘要。

    返回 {trace_id: {dimension: 摘要}}；单 trace 拉取失败/无 judge 观测 → 该维度为空
    （CSV 行 material_summary 留空，标注人点 trace_url）。逐 trace 定点 GET，不做
    全库翻页（防超时——见模块 docstring 中 scores 端点选型说明）。
    """
    from evals.judge_calibration.material import (
        build_summary,
        detect_dimension,
        prompt_from_observation_input,
    )

    summaries: dict[str, dict[str, str]] = {}
    for tid in trace_ids:
        try:
            resp = requests.get(
                f"{LANGFUSE_HOST}/api/public/observations",
                params={"traceId": tid, "limit": 100},
                headers={"Authorization": f"Basic {auth}"},
                timeout=30,
            )
            resp.raise_for_status()
            obs = resp.json().get("data") or []
        except Exception:  # noqa: BLE001 — 单 trace 拉取失败降级为空摘要，不阻断整批
            summaries[tid] = {}
            continue
        dim_prompts: dict[str, str] = {}
        for o in obs:
            # judge generation 观测名统一为 "judge"；四个维度靠 rubric 首句特征区分
            if str(o.get("name") or "") != "judge":
                continue
            prompt = prompt_from_observation_input(o.get("input"))
            dim = detect_dimension(prompt)
            if dim and prompt:
                dim_prompts.setdefault(dim, prompt)
        summaries[tid] = {dim: build_summary(prompt, dim) for dim, prompt in dim_prompts.items()}
    return summaries


def _reference_doc() -> str:
    """CSV 伴读文件：四维度 rubric 速查 + 指标速查（标注人对照用）。"""
    from evals.judge_calibration.material import METRIC_CHEATSHEET
    from evals.judges import RUBRICS

    lines = [
        "# Judge Rubric 速查（标注对照用）",
        "",
        "判分只做二分：**>3 = 认可 / ≤3 = 不认可**；拿不准的微差（3 vs 4）不伤指标"
        "（方向一致率按 >3 分界，MAE 容差 ±1）。每个维度只回答一个核心问题（见下）。",
        "",
    ]
    questions = {
        "report_relevance": "报告是不是在答用户问的标的/问题？（答非所问 → ≤3）",
        "debate_quality": "有没有针对对方论点逐条交锋并引数据？（自说自话/空洞 → ≤3）",
        "decision_grounding": "决策论据能否在分析师/辩论结论中找到出处？（无中生有/矛盾 → ≤3）",
        "consistency": "各层结论有无未说明的冲突？（FM 批准 vs Risk 否决 → ≤3）",
    }
    for dim, rubric in RUBRICS.items():
        lines.append(f"## {dim}\n\n> 核心问题：{questions.get(dim, '')}\n\n{rubric}\n")
    lines.append(METRIC_CHEATSHEET)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="judge-人工校准标注抽样导出")
    parser.add_argument("--limit", type=int, default=30, help="抽样 trace 数（默认 30）")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("evals/judge_calibration/data/judge-sample-round1.jsonl"),
        help="标注 JSONL 输出路径（每行含 trace_url 直达 Langfuse；人工回填 human_score 后跑 measure.py）",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="额外输出 CSV 标注表（含 material_summary 摘要列，人工回填 human_score/confidence）；"
        "同名 .rubrics.md 伴读文件一并产出",
    )
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=None,
        help="额外输出 xlsx 标注表（Excel 直开免拉格子：冻结表头/列宽/自动换行/行高估算/"
        "trace_url 可点击/待填列高亮）；同名 .rubrics.md 伴读文件一并产出",
    )
    parser.add_argument(
        "--blind-xlsx",
        type=Path,
        default=None,
        help="盲标版标注表（无 LLM judge 分/理由列，标注人先独立打分防锚定）；"
        "judge 分由 --blind-judge 独立存储供 measure 合并",
    )
    parser.add_argument(
        "--blind-judge",
        type=Path,
        default=None,
        help="judge 分参考 jsonl（每行 trace_id/dimension/judge_score/judge_reason；"
        "供 measure.py --judge-jsonl 合并计算一致性，非标注展示）",
    )
    args = parser.parse_args()
    payload = export_to_jsonl(args.out, args.limit)

    if args.csv or args.xlsx or args.blind_xlsx or args.blind_judge:
        from evals.judge_calibration.material import to_csv, to_xlsx

        _load_env()
        summaries = _fetch_judge_summaries([p["trace_id"] for p in payload], _auth())
        rows = [
            {
                **p,
                "material_summary": summaries.get(p["trace_id"], {}).get(p["dimension"], ""),
            }
            for p in payload
        ]
        if args.csv:
            args.csv.write_text(to_csv(rows), encoding="utf-8-sig")
            rubrics_path = Path(str(args.csv) + ".rubrics.md")
            rubrics_path.write_text(_reference_doc(), encoding="utf-8")
            print(
                f"CSV 标注表 → {args.csv}（{len(rows)} 行，material_summary 空 = 摘要拉取失败，"
                f"点 trace_url 查看）；rubric 速查 → {rubrics_path}"
            )
        if args.xlsx:
            to_xlsx(rows, args.xlsx)
            rubrics_path = Path(str(args.xlsx) + ".rubrics.md")
            rubrics_path.write_text(_reference_doc(), encoding="utf-8")
            print(
                f"xlsx 标注表 → {args.xlsx}（{len(rows)} 行，冻结表头/自动换行/行高已排好，"
                f"回填 human_score+confidence 后跑 measure.py --xlsx）；rubric 速查 → {rubrics_path}"
            )
        if args.blind_xlsx or args.blind_judge:
            from evals.judge_calibration.material import BLIND_HEADER

            if args.blind_xlsx:
                blind_rows = [{k: (r.get(k) or "") for k in BLIND_HEADER} for r in rows]
                to_xlsx(blind_rows, args.blind_xlsx, columns=BLIND_HEADER)
                rubrics_path = Path(str(args.blind_xlsx) + ".rubrics.md")
                rubrics_path.write_text(_reference_doc(), encoding="utf-8")
                print(
                    f"盲标版标注表 → {args.blind_xlsx}（无 judge 分/理由列，防锚定；"
                    f"回填 human_score+confidence 后跑 measure.py --xlsx --judge-jsonl）"
                )
            if args.blind_judge:
                judge_lines = [
                    json.dumps(
                        {
                            "trace_id": r["trace_id"],
                            "dimension": r["dimension"],
                            "judge_score": r.get("judge_score"),
                            "judge_reason": r.get("judge_reason", ""),
                        },
                        ensure_ascii=False,
                    )
                    for r in rows
                ]
                args.blind_judge.write_text("\n".join(judge_lines) + "\n", encoding="utf-8")
                print(f"judge 分参考 → {args.blind_judge}（measure 合并用，非标注展示）")


if __name__ == "__main__":
    main()
