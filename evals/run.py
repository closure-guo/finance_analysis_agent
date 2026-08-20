"""实验回归工作流(spec Requirement「实验回归工作流」)。

用法:
    uv run python -m evals.run "<实验名>"            # langfuse dataset.run_experiment
    uv run python -m evals.run "<实验名>" --local    # 无 langfuse 本地循环

产出:终端结果表 + reports/evals/<name>-<ts>.json(per-item 明细 + 均值 +
judge 失败数 + prompt_versions)。该 JSON 是 Judge 校准(Req 5,人工)的输入。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from evals.dataset_seed import DATASET_NAME, load_items
from evals.evaluators import make_evaluation, section_coverage, ticker_match
from evals.judges import run_judge
from evals.task import run_task

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


# ── 本地降级路径(无 langfuse)──


def _local_scores(output: dict, expected: dict) -> tuple[dict, int]:
    scores: dict = {}
    failures = 0
    for result in (
        section_coverage(output.get("report"), expected),
        ticker_match(output.get("ticker"), expected),
    ):
        if result:
            scores[result["name"]] = result["value"]
    mode = output.get("mode")
    for dim in _JUDGE_DIMS:
        if mode == "quick" and dim in _JUDGE_DEEP_ONLY:
            continue
        if not output.get("report"):
            continue
        result = run_judge(dim, output.get("judge_vars") or {})
        if result["score"] is None:
            failures += 1
        else:
            scores[dim] = result["score"]
    return scores, failures


def run_local(items: list[dict], experiment_name: str) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        # 单条隔离：一条 dataset 失败（如 OutputTruncated 耗尽重试）记录为
        # skipped=error 后继续，不炸整批——否则 16 条基线对比被单条坏输出绑架。
        try:
            output = run_task(item=item, expected_output=item.get("expected_output"))
        except Exception as exc:  # noqa: BLE001 -- 记录后继续下一条
            print(f"[run] item 失败（已隔离继续）: {type(exc).__name__}: {exc}")
            rows.append(
                {
                    "item": item["input"]["query"],
                    "mode": item["input"]["mode"],
                    "skipped": f"error:{type(exc).__name__}",
                    "scores": {},
                    "judge_failures": 0,
                }
            )
            continue
        if output.get("skipped"):
            rows.append(
                {
                    "item": item["input"]["query"],
                    "mode": item["input"]["mode"],
                    "skipped": output["skipped"],
                    "scores": {},
                    "judge_failures": 0,
                }
            )
            continue
        scores, failures = _local_scores(output, item.get("expected_output") or {})
        rows.append(
            {
                "item": item["input"]["query"],
                "mode": item["input"]["mode"],
                "skipped": None,
                "scores": scores,
                "judge_failures": failures,
            }
        )
    return rows


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
    parser.add_argument("--local", action="store_true", help="无 langfuse 本地循环")
    args = parser.parse_args()

    prompt_versions = _collect_prompt_versions()
    print("prompt_versions:", json.dumps(prompt_versions, ensure_ascii=False))

    client = None
    if not args.local:
        from finance_agent.langfuse_tracing import get_langfuse

        client = get_langfuse()

    if client is not None:
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
    else:
        print("langfuse 未配置(或 --local),走本地循环")
        rows = run_local(load_items(), args.name)

    means = _mean_rows(rows)
    _print_table(rows, means)
    path = _write_report(rows, means, args.name, prompt_versions)
    print(f"结果已写入 {path}")
    if client is not None:
        client.flush()


if __name__ == "__main__":
    main()
