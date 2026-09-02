"""消融实验小规模试跑驱动（评估体系开机任务清单 · 任务 3）。

配置硬上限：3 标的 × 3 变体（analysts / plus_debate / full）× 3 次重复，
管线模型 deepseek 非 pro 档（ark-plan deepseek-v4-flash，偏差披露见
backtest_pilot_2023._pin_pipeline_model）。统计沿用 evals/ablation.aggregate_results
（同标的中位 + 配对 bootstrap B=10,000，95% CI）。

在设施主流程外补两件测量（不改 evals/ablation.py）：
1. citation_coverage：包装 verify_citations 逐次记录（设施聚合报告未含 coverage）；
2. token 成本：包装 run_variant_once + run_judge 按 run 归属计量
   （复用 backtest_pilot_2023 的 usage meter）。

**断点续跑**（2026-09-02 增加）：ark burst 限流已两次在临近结束时打崩整段
3 小时试跑。改为自驱循环 + 每完成一条 run 即落盘 reports/ablation/resume.json，
重启时跳过已完成 (variant, ticker, repeat)，不重烧 token。

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
RESUME_PATH = Path("reports/ablation/resume.json")


def _load_resume() -> dict:
    if RESUME_PATH.exists():
        try:
            return json.loads(RESUME_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    pilot_util._pin_pipeline_model()
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

    def run_one_costed(variant: str, snapshot: dict, query: str) -> dict:
        """单次变体运行 + judge，返回 (out, cost_row)。"""
        before_calls = len(pilot_util._usage_ledger)
        before_cov = len(coverage_ledger)
        out = original_run_once(variant, snapshot, query)
        new_entries = pilot_util._usage_ledger[before_calls:]
        cov_entries = coverage_ledger[before_cov:]

        judge_scores: dict[str, float | None] = {}
        for dim in ablation.JUDGE_DIMS:
            if variant == "analysts" and dim != "report_relevance":
                judge_scores[dim] = None
                continue
            result = ablation.run_judge(dim, out["judge_vars"])
            judge_scores[dim] = float(result["score"]) if result["score"] is not None else None

        cost_row = {
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
            "judge": judge_scores,
        }
        return out, cost_row

    # ── 断点续跑状态 ──
    resume = _load_resume()
    done_keys = {tuple(k) for k in resume.get("done_keys", [])}
    runs: list[dict[str, Any]] = resume.get("runs", [])
    snap_digests: dict[str, str] = resume.get("snapshot_digests", {})
    print(
        f"消融试跑: {TICKERS} × 3 变体 × {REPEATS} 重复 | 续跑起点: 已完成 {len(done_keys)} 条",
        flush=True,
    )

    def _persist() -> None:
        RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESUME_PATH.write_text(
            json.dumps(
                {
                    "done_keys": sorted(done_keys),
                    "runs": runs,
                    "snapshot_digests": snap_digests,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    query = "综合评估投资价值"
    for ticker in TICKERS:
        if ticker not in snap_digests:
            snapshot = ablation.build_snapshot(ticker)
            snap_digests[ticker] = ablation.snapshot_digest(snapshot)
        for variant in ablation._VARIANTS:
            for i in range(REPEATS):
                key = (variant, ticker, i)
                if key in done_keys:
                    print(f"跳过已完成: {key}", flush=True)
                    continue
                print(f"[{datetime.now():%H:%M:%S}] 运行 {key}", flush=True)
                # 每轮重建快照（进程内重放共享同 digest；跨进程重启重取一次数据）
                snapshot = ablation.build_snapshot(ticker)
                out, cost_row = run_one_costed(variant, snapshot, query)
                runs.append(
                    {
                        "variant": variant,
                        "ticker": ticker,
                        "repeat": i,
                        "citation_pass": out["citation_pass"],
                        "judge": out.get("judge") or cost_row["judge"],
                        **cost_row,
                    }
                )
                done_keys.add(key)
                _persist()

    report = ablation.aggregate_results(runs)
    from evals.run import _collect_prompt_versions

    report["prompt_versions"] = _collect_prompt_versions()
    report["snapshot_digests"] = snap_digests
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")

    # 按变体归集 coverage 与成本
    per_variant: dict[str, dict[str, Any]] = {}
    for rc in runs:
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
        v["citation_pass_rate"] = sum(v["passes"]) / len(v["passes"]) if v["passes"] else None
        del v["coverages"]
        del v["passes"]

    out = {
        "pilot": "ablation-pilot",
        "config": {
            "tickers": TICKERS,
            "repeats": REPEATS,
            "pipeline_model": os.environ.get("LLM_MODEL"),
        },
        "report": report,
        "per_variant_cost": per_variant,
        "run_costs": runs,
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
