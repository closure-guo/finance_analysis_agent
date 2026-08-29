"""实验基线对比：配对 bootstrap 95% CI（spec evaluation「实验对比统计显著性」）。

输入两份 evals/run.py 报告 JSON，按 dataset item 配对；CI 含 0 → 结论只能是
「无显著差异」，禁止「略有提升」等无统计支撑措辞。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from evals.stats import paired_bootstrap_ci


class MetricComparison(BaseModel):
    mean_a: float
    mean_b: float
    diff: float
    ci: tuple[float, float]
    conclusion: str  # 显著改进 / 显著退步 / 无显著差异


class CompareReport(BaseModel):
    experiment_a: str
    experiment_b: str
    B: int
    metrics: dict[str, MetricComparison]


def _load_rows(path: Path) -> tuple[str, dict[str, dict[str, float]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, dict[str, float]] = {}
    for row in data.get("rows", []):
        if row.get("skipped"):
            continue
        rows[str(row["item"])] = {
            k: float(v) for k, v in (row.get("scores") or {}).items() if v is not None
        }
    return str(data.get("experiment", path.stem)), rows


def compare_reports(
    path_a: Path,
    path_b: Path,
    *,
    B: int = 10_000,  # noqa: N803 — 接口冻结：参数名 B 为后续任务依赖契约
    seed: int = 42,
) -> CompareReport:
    name_a, rows_a = _load_rows(path_a)
    name_b, rows_b = _load_rows(path_b)
    if set(rows_a) != set(rows_b):
        only_a = sorted(set(rows_a) - set(rows_b))[:3]
        only_b = sorted(set(rows_b) - set(rows_a))[:3]
        raise ValueError(
            f"item 不对齐（配对 bootstrap 要求同一 dataset 全量跑完）: 仅A有{only_a} 仅B有{only_b}"
        )
    metric_names = sorted({m for scores in rows_a.values() for m in scores})
    comparisons: dict[str, MetricComparison] = {}
    for metric in metric_names:
        pairs = [(rows_a[item].get(metric), rows_b[item].get(metric)) for item in sorted(rows_a)]
        valid = [(a, b) for a, b in pairs if a is not None and b is not None]
        if not valid:
            continue
        seq_a = [a for a, _ in valid]
        seq_b = [b for _, b in valid]
        mean_a = sum(seq_a) / len(seq_a)
        mean_b = sum(seq_b) / len(seq_b)
        lo, hi = paired_bootstrap_ci(seq_a, seq_b, B=B, seed=seed)
        if lo > 0:
            conclusion = "显著改进"
        elif hi < 0:
            conclusion = "显著退步"
        else:
            conclusion = "无显著差异"
        comparisons[metric] = MetricComparison(
            mean_a=round(mean_a, 4),
            mean_b=round(mean_b, 4),
            diff=round(mean_a - mean_b, 4),
            ci=(round(lo, 4), round(hi, 4)),
            conclusion=conclusion,
        )
    return CompareReport(experiment_a=name_a, experiment_b=name_b, B=B, metrics=comparisons)


def main() -> None:
    parser = argparse.ArgumentParser(description="实验对比（配对 bootstrap 95% CI）")
    parser.add_argument("report_a")
    parser.add_argument("report_b")
    parser.add_argument("--B", type=int, default=10_000)
    args = parser.parse_args()
    report = compare_reports(Path(args.report_a), Path(args.report_b), B=args.B)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    out_dir = Path("reports/evals")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"compare-{report.experiment_a}-vs-{report.experiment_b}-{ts}.json"
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"对比报告已写入 {path}")


if __name__ == "__main__":
    main()
