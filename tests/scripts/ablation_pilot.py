"""消融实验小规模试跑驱动（评估体系开机任务清单 · 任务 3）。

配置硬上限：3 标的 × 3 变体（analysts / plus_debate / full）× 3 次重复，
管线模型 deepseek-chat（非 pro）。统计沿用 evals/ablation.aggregate_results
（同标的中位 + 配对 bootstrap B=10,000，95% CI）。

在设施主流程外补两件测量（不改 evals/ablation.py）：
1. citation_coverage：包装 verify_citations 逐次记录（设施聚合报告未含 coverage）；
2. token 成本：包装 run_variant_once + run_judge 按 run 归属计量
   （复用 backtest_pilot_2023 的 usage meter）。

产物：reports/ablation/pilot-<ts>.json（聚合报告 + coverage + 成本台账）。
pilot.md（人读版）由试跑记录手写落于 evals/ablation/results/pilot.md。

用法：
    uv run python tests/scripts/ablation_pilot.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests" / "scripts"))

import backtest_pilot_2023 as pilot_util  # noqa: E402

TICKERS = ["002412", "600519", "300308"]  # 汉森制药 / 贵州茅台 / 中际旭创
REPEATS = 3


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()  # 管线 deepseek-chat（judge 沿用 .env JUDGE_* 配置）
    pilot_util.install_usage_meter()

    import evals.ablation as ablation

    coverage_ledger: list[dict[str, Any]] = []
    run_costs: list[dict[str, Any]] = []

    original_verify = ablation.verify_citations

    def metered_verify(state: dict) -> dict:
        out = original_verify(state)
        coverage_ledger.append(
            {
                "citation_pass": out.get("citation_pass"),
                "citation_coverage": out.get("citation_coverage"),
            }
        )
        return out

    ablation.verify_citations = metered_verify

    original_run_once = ablation.run_variant_once

    def metered_run_once(variant: str, snapshot: dict, query: str) -> dict:
        before_calls = len(pilot_util._usage_ledger)
        before_prompt = sum(r["prompt_tokens"] for r in pilot_util._usage_ledger)
        before_completion = sum(r["completion_tokens"] for r in pilot_util._usage_ledger)
        before_cov = len(coverage_ledger)
        out = original_run_once(variant, snapshot, query)
        new_entries = pilot_util._usage_ledger[before_calls:]
        cov_entries = coverage_ledger[before_cov:]
        run_costs.append(
            {
                "variant": variant,
                "llm_calls": len(new_entries),
                "prompt_tokens": sum(r["prompt_tokens"] for r in new_entries),
                "completion_tokens": sum(r["completion_tokens"] for r in new_entries),
                "estimated_calls": sum(1 for r in new_entries if r["estimated"]),
                "citation_coverage": (
                    sum(
                        c["citation_coverage"]
                        for c in cov_entries
                        if c["citation_coverage"] is not None
                    )
                    / max(1, sum(1 for c in cov_entries if c["citation_coverage"] is not None))
                    if cov_entries
                    else None
                ),
                "citation_pass": out.get("citation_pass"),
            }
        )
        return out

    ablation.run_variant_once = metered_run_once

    print(f"消融试跑: {TICKERS} × 3 变体 × {REPEATS} 重复", flush=True)
    report = ablation.run_ablation(TICKERS, repeats=REPEATS)

    # 按变体归集 coverage 与成本
    per_variant: dict[str, dict[str, Any]] = {}
    for rc in run_costs:
        v = per_variant.setdefault(
            rc["variant"],
            {
                "runs": 0,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_calls": 0,
                "coverages": [],
                "passes": [],
            },
        )
        v["runs"] += 1
        v["llm_calls"] += rc["llm_calls"]
        v["prompt_tokens"] += rc["prompt_tokens"]
        v["completion_tokens"] += rc["completion_tokens"]
        v["estimated_calls"] += rc["estimated_calls"]
        if rc["citation_coverage"] is not None:
            v["coverages"].append(rc["citation_coverage"])
        v["passes"].append(bool(rc["citation_pass"]))
    for v in per_variant.values():
        v["citation_coverage_mean"] = (
            round(sum(v["coverages"]) / len(v["coverages"]), 4) if v["coverages"] else None
        )
        v["total_tokens"] = v["prompt_tokens"] + v["completion_tokens"]
        del v["coverages"]

    out = {
        "pilot": "ablation-pilot",
        "config": {
            "tickers": TICKERS,
            "repeats": REPEATS,
            "pipeline_model": os.environ.get("LLM_MODEL"),
        },
        "report": report,
        "per_variant_cost": per_variant,
        "run_costs": run_costs,
        "usage_summary": {
            "llm_calls_total": len(pilot_util._usage_ledger),
            "prompt_tokens": sum(r["prompt_tokens"] for r in pilot_util._usage_ledger),
            "completion_tokens": sum(r["completion_tokens"] for r in pilot_util._usage_ledger),
            "estimated_calls": sum(1 for r in pilot_util._usage_ledger if r["estimated"]),
        },
    }
    out_dir = Path("reports/ablation")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pilot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"消融试跑产物已写入 {path}")
    print(
        json.dumps(
            {"per_variant_cost": per_variant, "usage_summary": out["usage_summary"]},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
