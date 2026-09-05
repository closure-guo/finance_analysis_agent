#!/usr/bin/env python
"""延迟/成本回归与趋势度量（add-latency-cost-regression）。

从 Langfuse traces 聚合：端到端时延（trace.latency，秒）、token 用量
（GENERATION observations usage 汇总）、折算成本（模型单价表配置化，
按 usage 计价——Langfuse totalCost 需平台配价，本项目不做依赖）。
quick/deep 分开统计；超基线阈值判回归；连续方向劣化判趋势告警。

用法:
    uv run python evals/performance/measure.py \
        [--traces path/to/traces.json] [--baseline path/to/baseline.json] \
        [--out reports/perf-report.md]

纯函数可离线测试；省略 --traces 时由 run.py 拉取。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 模型单价表（元/百万 tokens，输入/输出）；未收录模型走 DEFAULT_PRICE 兜底
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "glm-4.5": (2.0, 6.0),
    "glm-4.7": (2.0, 6.0),
    "deepseek-chat": (1.0, 2.0),
    "deepseek-reasoner": (2.0, 8.0),
}
DEFAULT_PRICE = (1.0, 2.0)

REGRESSION_PCT = float(os.getenv("PERF_REGRESSION_PCT", "0.30"))  # 超基线 30% 判回归
WINDOW_DAYS = 14  # 归档回看窗口
TREND_N = 3  # 连续 N 轮单调劣化即趋势告警
TREND_MIN_PCT = 0.05  # 每轮劣化至少 5%（防噪声抖动）

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_fetch_perf_traces: Callable[..., list[dict[str, Any]]] | None = None
try:  # noqa: E402 - 运行时依赖可选
    from evals.performance.run import fetch_perf_traces as _fetch_perf_traces  # noqa: E402
except Exception:  # noqa: BLE001, S110
    _fetch_perf_traces = None


@dataclass
class PerfSample:
    name: str
    timestamp: str
    latency_s: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    model: str | None = None

    @property
    def mode(self) -> str:
        n = (self.name or "").lower()
        if "deep" in n:
            return "deep"
        return "quick"


def estimate_cost(input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    price = PRICE_TABLE.get(model or "", DEFAULT_PRICE)
    return round(input_tokens / 1_000_000 * price[0] + output_tokens / 1_000_000 * price[1], 6)


def extract_trace(t: dict[str, Any]) -> PerfSample:
    """从单条 trace 提取样本：latency + generations usage 汇总 + 成本估算。"""
    usage_input = usage_output = 0
    model_counts: dict[str, int] = {}
    for o in t.get("observations") or []:
        if o.get("type") != "GENERATION":
            continue
        u = o.get("usage") or {}
        usage_input += int(u.get("input") or 0)
        usage_output += int(u.get("output") or 0)
        m = o.get("model")
        if m:
            model_counts[m] = model_counts.get(m, 0) + 1
    model = max(model_counts, key=lambda m: model_counts[m]) if model_counts else None
    latency = t.get("latency")
    return PerfSample(
        name=str(t.get("name") or ""),
        timestamp=str(t.get("timestamp") or ""),
        latency_s=float(latency) if isinstance(latency, (int, float)) else None,
        input_tokens=usage_input,
        output_tokens=usage_output,
        cost=estimate_cost(usage_input, usage_output, model),
        model=model,
    )


@dataclass
class PerfAggregate:
    total: int = 0
    by_mode: dict[str, int] = field(default_factory=dict)
    p50_latency_s: float | None = None
    p90_latency_s: float | None = None
    avg_total_tokens: float | None = None
    avg_cost: float | None = None
    avg_latency_s: float | None = None


def aggregate(traces: list[dict[str, Any]]) -> tuple[PerfAggregate, list[PerfSample]]:
    samples = [extract_trace(t) for t in traces]
    agg = PerfAggregate(total=len(samples))
    for s in samples:
        agg.by_mode[s.mode] = agg.by_mode.get(s.mode, 0) + 1
    latencies = [s.latency_s for s in samples if s.latency_s is not None]
    tokens = [s.input_tokens + s.output_tokens for s in samples]
    costs = [s.cost for s in samples]
    if latencies:
        agg.avg_latency_s = round(statistics.mean(latencies), 4)
        agg.p50_latency_s = round(statistics.median(latencies), 4)
        agg.p90_latency_s = round(
            sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.9))], 4
        )
    if tokens:
        agg.avg_total_tokens = round(statistics.mean(tokens), 1)
    if costs:
        agg.avg_cost = round(statistics.mean(costs), 6)
    return agg, samples


def compare_with_baseline(agg: PerfAggregate, baseline: dict[str, Any]) -> list[dict[str, Any]]:
    """核心指标对比基线，超 REGRESSION_PCT 判回归。"""
    rows: list[dict[str, Any]] = []
    for key, label in (
        ("avg_latency_s", "平均时延(s)"),
        ("p90_latency_s", "P90 时延(s)"),
        ("avg_total_tokens", "平均 token"),
        ("avg_cost", "平均成本(元)"),
    ):
        cur = getattr(agg, key)
        base = baseline.get(key)
        if cur is None or base is None:
            continue
        pct = (cur - base) / base if base else None
        rows.append(
            {
                "metric": key,
                "label": label,
                "current": cur,
                "baseline": base,
                "pct_change": round(pct, 4) if pct is not None else None,
                "regressed": pct is not None and pct > REGRESSION_PCT,
            }
        )
    return rows


def detect_trend(
    history: list[float], trend_n: int = TREND_N, min_pct: float = TREND_MIN_PCT
) -> bool:
    """连续 trend_n 轮单调劣化（每轮涨幅 ≥ min_pct）→ 趋势告警。"""
    if len(history) < trend_n:
        return False
    tail = history[-trend_n:]
    for i in range(1, len(tail)):
        prev, cur = tail[i - 1], tail[i]
        if prev <= 0 or cur < prev * (1 + min_pct):
            return False
    return True


def render_report(
    agg: PerfAggregate,
    compares: list[dict[str, Any]],
    trend_alert: bool,
    baseline_date: str | None = None,
) -> str:
    lines = [
        "# 延迟/成本性能报告",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 样本: {agg.total} 条 trace（quick {agg.by_mode.get('quick', 0)} / deep {agg.by_mode.get('deep', 0)}）",
        f"- P50 时延: {agg.p50_latency_s or '—'} s | P90: {agg.p90_latency_s or '—'} s",
        f"- 平均 token: {agg.avg_total_tokens or '—'} | 平均成本: {agg.avg_cost or '—'} 元",
        "",
        "## 与基线对比",
        "",
        "| 指标 | 当前 | 基线 | 变化 | 回归 |",
        "|---|---|---|---|---|",
    ]
    for r in compares:
        pct_txt = "—" if r["pct_change"] is None else f"{r['pct_change'] * 100:+.1f}%"
        lines.append(
            f"| {r['label']} | {r['current']} | {r['baseline']} | {pct_txt} | {'⚠️' if r['regressed'] else '✓'} |"
        )
    lines += ["", f"- 趋势告警（连续 {TREND_N} 轮单调劣化）: {'⚠️ 是' if trend_alert else '否'}", ""]
    if baseline_date:
        lines.append(f"> 基线: {baseline_date}")
    return "\n".join(lines)


def run_offline(
    traces: list[dict[str, Any]], baseline: dict[str, Any] | None = None
) -> dict[str, Any]:
    agg, samples = aggregate(traces)
    compares = compare_with_baseline(agg, baseline or {})
    # 趋势告警依赖归档历史（nightly 时序），离线路径仅报告不判趋势
    return {
        "aggregate": agg,
        "samples": samples,
        "compares": compares,
        "trend_alert": False,
    }


def load_baseline(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _eval_model() -> str:
    """基线绑定的模型（与 agent_factory/evals.run 同优先级解析）。"""
    return os.getenv("LLM_MODEL") or "deepseek/deepseek-chat"


def _save_baseline(baseline_path: Path, agg: PerfAggregate) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "avg_latency_s": agg.avg_latency_s,
                "p90_latency_s": agg.p90_latency_s,
                "avg_total_tokens": agg.avg_total_tokens,
                "avg_cost": agg.avg_cost,
                "model": _eval_model(),
                "as_of": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="延迟/成本性能度量")
    parser.add_argument("--traces", type=Path, help="外部 trace JSON 列表（覆盖 Langfuse 拉取）")
    parser.add_argument("--baseline", type=Path, default=Path("docs/evals/perf-baseline.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/perf-report.md"))
    parser.add_argument("--save-baseline", action="store_true", help="报告后将本次聚合落为基线")
    args = parser.parse_args()

    if args.traces:
        traces = json.loads(args.traces.read_text(encoding="utf-8"))
    elif _fetch_perf_traces is not None:
        traces = _fetch_perf_traces()
    else:
        parser.error("未提供 --traces 且 run 模块不可导入")

    baseline = load_baseline(args.baseline)
    baseline_model = baseline.get("model")
    if baseline_model and baseline_model != _eval_model():
        print(
            f"⚠️ 基线模型不匹配：基线由 {baseline_model} 产出，当前为 {_eval_model()}。"
            "时延/成本跨模型不可比——请用 --save-baseline 重测基线后再对比。"
        )
    agg, samples = aggregate(traces)
    compares = compare_with_baseline(agg, baseline)
    report = render_report(agg, compares, False, baseline.get("as_of"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    if args.save_baseline and args.baseline is not None:
        _save_baseline(args.baseline, agg)
    print(report)


if __name__ == "__main__":
    main()
