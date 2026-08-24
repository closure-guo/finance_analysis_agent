"""实验回归工作流(spec Requirement「实验回归工作流」)。

用法:
    uv run python -m evals.run "<实验名>"   # 经 langfuse dataset.run_experiment 执行

run_experiment 是实验唯一执行入口:无 langfuse(Langfuse 未配置/不可达)时
打印明确错误并以非零退出码终止,不提供本地循环降级路径。

产出:终端结果表 + reports/evals/<name>-<ts>.json(per-item 明细 + 均值 +
judge 失败数 + prompt_versions)。该 JSON 是 Judge 校准(Req 5,人工)的输入。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from evals.dataset_seed import DATASET_NAME
from evals.evaluators import make_evaluation, section_coverage, ticker_match
from evals.judges import run_judge
from evals.task import run_task
from finance_agent.langfuse_tracing import get_langfuse

_PROMPT_NAMES = [
    "macro_analyst",
    "fundamental_analyst",
    "technical_analyst",
    "sentiment_analyst",
    "bull_debater",
    "bear_debater",
    "research_manager",
    "trader",
    "risk_debater",
    "risk_judge",
    "fund_manager",
    "quick_mode",
    "deep_mode",
    "follow_up_mode",
]
_JUDGE_DIMS = ["report_relevance", "debate_quality", "decision_grounding", "consistency"]
# quick 模式无辩论/决策层:只有 report_relevance 适用(design §7 过滤器)
_JUDGE_DEEP_ONLY = {"debate_quality", "decision_grounding", "consistency"}


def _collect_prompt_versions() -> dict[str, str]:
    """记录实验所用 prompt 版本(production label;load_prompt_with_meta 只读复用)。"""
    from finance_agent.prompts.loader import load_prompt_with_meta

    versions: dict[str, str] = {}
    for name in _PROMPT_NAMES:
        try:
            versions[name] = str(load_prompt_with_meta(name).prompt_version)
        except Exception:
            versions[name] = "unknown"
    return versions


# ── langfuse evaluator 适配器(签名 (*, input, output, expected_output, metadata))──


def eval_section_coverage(*, input, output, expected_output, metadata):
    result = section_coverage(output.get("report") if output else None, expected_output or {})
    return make_evaluation(result) if result else None


def eval_ticker_match(*, input, output, expected_output, metadata):
    result = ticker_match(output.get("ticker") if output else None, expected_output or {})
    return make_evaluation(result) if result else None


def _judge_adapter(dimension: str):
    def _eval(*, input, output, expected_output, metadata):
        mode = (output or {}).get("mode") or (input or {}).get("mode")
        if mode == "quick" and dimension in _JUDGE_DEEP_ONLY:
            return None  # quick 无辩论,跳过
        if not (output or {}).get("report"):
            return None  # skipped item
        result = run_judge(dimension, (output or {}).get("judge_vars") or {})
        if result["score"] is None:
            # score=null:解析失败,记入失败率(已实测 langfuse 4.13
            # Evaluation.value 接受 None,无需 _failed 占位 fallback)
            return make_evaluation({"name": dimension, "value": None, "comment": result["reason"]})
        return make_evaluation(
            {"name": dimension, "value": float(result["score"]), "comment": result["reason"]}
        )

    _eval.__name__ = f"eval_{dimension}"
    return _eval


def all_evaluators() -> list:
    return [eval_section_coverage, eval_ticker_match] + [_judge_adapter(d) for d in _JUDGE_DIMS]


def _mean_rows(rows: list[dict]) -> dict:
    """各 Score 均值(None 不计入)+ judge 失败总数。"""
    buckets: dict[str, list[float]] = {}
    failures = 0
    for row in rows:
        failures += row.get("judge_failures", 0)
        for name, value in (row.get("scores") or {}).items():
            if value is not None:
                buckets.setdefault(name, []).append(float(value))
    means = {name: round(sum(vals) / len(vals), 4) for name, vals in buckets.items() if vals}
    means["judge_failures"] = failures
    return means


def _print_table(rows: list[dict], means: dict) -> None:
    for row in rows:
        if row.get("skipped"):
            print(f"[skip] {row['item']} ({row['mode']}): {row['skipped']}")
            continue
        score_str = " ".join(f"{k}={v}" for k, v in row["scores"].items())
        print(f"[{row['mode']:9}] {row['item'][:30]:32} {score_str}")
    print("─" * 60)
    print("均值:", json.dumps(means, ensure_ascii=False))


def _write_report(rows: list[dict], means: dict, name: str, prompt_versions: dict) -> Path:
    out_dir = Path("reports/evals")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{name}-{ts}.json"
    path.write_text(
        json.dumps(
            {
                "experiment": name,
                "timestamp": ts,
                "prompt_versions": prompt_versions,
                "means": means,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def main() -> None:
    # 与 api.py 一致：CLI 入口加载 .env（否则 shell 无 LANGFUSE/LLM key，误判「未配置」）
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="evals 实验回归")
    parser.add_argument("name", help="实验名(如 baseline-v1)")
    args = parser.parse_args()

    # run_experiment 是实验唯一执行入口(spec「实验回归工作流」Scenario「无 Langfuse 时显式报错」):
    # langfuse 不可用时显式报错并退出,绝不降级为本地循环产出不可对比的分数。
    client = get_langfuse()
    if client is None:
        sys.exit(
            "错误: Langfuse 未配置/不可达，实验必须经 run_experiment 执行。"
            "请配置 LANGFUSE_PUBLIC_KEY/SECRET_KEY 且服务可达。"
        )

    prompt_versions = _collect_prompt_versions()
    print("prompt_versions:", json.dumps(prompt_versions, ensure_ascii=False))

    dataset = client.get_dataset(DATASET_NAME)
    result = dataset.run_experiment(
        name=args.name,
        task=run_task,
        evaluators=all_evaluators(),
        max_concurrency=1,  # 管线分钟级,禁高并发
        metadata={"prompt_versions": prompt_versions},
    )
    rows = [
        {
            "item": str(r.item.input.get("query")),
            "mode": r.item.input.get("mode"),
            "skipped": None,
            "scores": {e.name: e.value for e in r.evaluations if e.value is not None},
            "judge_failures": sum(1 for e in r.evaluations if e.value is None),
        }
        for r in result.item_results
    ]

    means = _mean_rows(rows)
    _print_table(rows, means)
    path = _write_report(rows, means, args.name, prompt_versions)
    print(f"结果已写入 {path}")
    client.flush()


if __name__ == "__main__":
    main()
