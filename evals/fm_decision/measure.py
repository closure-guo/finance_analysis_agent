#!/usr/bin/env python
"""FM 决策分布与质量度量（calibrate-fm-approval Task 3）。

从 Langfuse `fund_manager` trace 的 output.answer（```json 包裹的
{"decision": approve|return|reject, "reasoning": ...}）聚合决策分布；
对带风控指标的对抗样本断言风控否决召回（高风险 approve 即违例）；
对全部决策断言理由完整（空 reasoning 即违例）。

边界：
- 分布不设硬性占比下限——取证（2026-09-04）证明 FM 对高风险标的的否决
  是职责所需（力鼎光电回撤 41%/波动 76% 被正确否决），防漂移靠趋势记录；
- 风控否决召回需带 max_drawdown/volatility 的标注样本（live trace 的
  output 不含风险指标，故该门禁以 fixtures 对抗样本集驱动）；
- 理由完整门禁可直接作用于 live trace。

用法:
    uv run python evals/fm_decision/measure.py \
        [--traces path/to/traces.json] [--out reports/fm-decision-report.md]

纯函数可离线测试（喂 trace dict fixture）；--traces 省略时按 run.py 拉取。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# 风控否决召回阈值：对齐观测案例（力鼎光电回撤 41.2%/波动 75.6% 被正确否决）
DEFAULT_MAX_DRAWDOWN_THRESHOLD = 0.30
DEFAULT_VOLATILITY_THRESHOLD = 0.60

_DECISION_RE = re.compile(r'"decision"\s*:\s*"(\w+)"')
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_fetch_fund_manager_traces: Callable[[], list[dict[str, Any]]] | None = None

try:  # noqa: E402 — 运行时依赖可选（纯函数测试不需 Langfuse）
    from evals.fm_decision.run import (
        fetch_fund_manager_traces as _fetch_fund_manager_traces,  # noqa: E402
    )
except Exception:  # noqa: BLE001, S110 - 纯函数/离线路径不要求 run 模块可导入
    _fetch_fund_manager_traces = None


@dataclass
class TraceSample:
    """单条 FM 决策样本。max_drawdown/volatility 仅对抗标注样本携带。"""

    decision: str
    reasoning: str
    timestamp: str = ""
    trace_id: str = ""
    max_drawdown: float | None = None
    volatility: float | None = None


def parse_answer(answer: str) -> dict[str, str] | None:
    """从 FM 原始 answer（code fence 包裹或裸 JSON）解析 decision/reasoning。

    解析失败返回 None（计入 parse_fail，不阻断统计）。
    """
    if not answer:
        return None
    text = answer.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 宽松回退：正则取 decision，reasoning 用原文
        m = _DECISION_RE.search(answer)
        if not m:
            return None
        return {"decision": m.group(1), "reasoning": answer}
    if not isinstance(data, dict) or not isinstance(data.get("decision"), str):
        return None
    return {"decision": data["decision"], "reasoning": str(data.get("reasoning") or "")}


def extract_samples(traces: list[dict[str, Any]]) -> tuple[list[TraceSample], int]:
    """从 trace 列表提取样本；返回 (samples, parse_fail 数)。"""
    samples: list[TraceSample] = []
    parse_fail = 0
    for t in traces:
        out = t.get("output") or {}
        parsed = parse_answer((out.get("answer") or "") if isinstance(out, dict) else "")
        if parsed is None:
            parse_fail += 1
            continue
        samples.append(
            TraceSample(
                decision=parsed["decision"],
                reasoning=parsed["reasoning"],
                timestamp=str(t.get("timestamp") or ""),
                trace_id=str(t.get("id") or ""),
            )
        )
    return samples, parse_fail


def aggregate(samples: list[TraceSample]) -> dict[str, Any]:
    """决策分布：总样本、计数、按日分桶（不设占比阈值，仅趋势记录）。"""
    counts = Counter(x.decision for x in samples)
    by_day: dict[str, Counter[str]] = defaultdict(Counter)
    for x in samples:
        by_day[x.timestamp[:10]][x.decision] += 1
    # 分桶补齐三档零值，保证报告表格列齐
    normalized = {
        day: {k: c.get(k, 0) for k in ("approve", "return", "reject")}
        for day, c in sorted(by_day.items())
    }
    return {
        "total": len(samples),
        "counts": dict(counts),
        "by_day": normalized,
    }


def veto_recall(
    samples: list[TraceSample],
    max_drawdown_threshold: float = DEFAULT_MAX_DRAWDOWN_THRESHOLD,
    volatility_threshold: float = DEFAULT_VOLATILITY_THRESHOLD,
) -> dict[str, Any]:
    """风控否决召回：高风险（回撤/波动超阈值）样本 SHALL NOT approve。

    无风险指标的样本不计入 checked；违例=高风险且 approve。
    """
    checked = 0
    violations: list[dict[str, Any]] = []
    for s in samples:
        has_risk = s.max_drawdown is not None or s.volatility is not None
        if not has_risk:
            continue
        checked += 1
        high_risk = (s.max_drawdown or 0) > max_drawdown_threshold or (
            s.volatility or 0
        ) > volatility_threshold
        if high_risk and s.decision == "approve":
            violations.append(
                {
                    "trace_id": s.trace_id,
                    "timestamp": s.timestamp,
                    "max_drawdown": s.max_drawdown,
                    "volatility": s.volatility,
                }
            )
    return {
        "checked": checked,
        "violation_count": len(violations),
        "violations": violations,
        "violation_rate": len(violations) / checked if checked else None,
    }


def reason_complete(samples: list[TraceSample]) -> dict[str, Any]:
    """否决理由完整：decision 必须带非空 reasoning。"""
    missing = [s for s in samples if not (s.reasoning or "").strip()]
    return {
        "checked": len(samples),
        "missing_count": len(missing),
        "missing": [
            {"trace_id": s.trace_id, "timestamp": s.timestamp, "decision": s.decision}
            for s in missing
        ],
    }


def render_report(
    agg: dict[str, Any],
    veto: dict[str, Any],
    reason: dict[str, Any],
    parse_fail: int,
) -> str:
    """渲染 markdown 报告（reports/ 产物）。"""
    total = agg["total"]
    counts = agg["counts"]
    dist = "、".join(
        f"{k} {counts.get(k, 0)}（{counts.get(k, 0) / total:.0%}" + "）"
        for k in ("approve", "return", "reject")
        if counts.get(k)
    )
    lines = [
        "# FM 决策分布与质量报告",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 样本: {total} 条 fund_manager trace（解析失败 {parse_fail} 条）",
        f"- 分布: {dist or '无'}",
        "",
        "## 按日分桶",
        "",
        "| 日期 | approve | return | reject |",
        "|---|---|---|---|",
    ]
    for day, c in agg["by_day"].items():
        lines.append(
            f"| {day} | {c.get('approve', 0)} | {c.get('return', 0)} | {c.get('reject', 0)} |"
        )
    lines += [
        "",
        f"## 风控否决召回（阈值 回撤>{DEFAULT_MAX_DRAWDOWN_THRESHOLD} / 波动>{DEFAULT_VOLATILITY_THRESHOLD}）",
        "",
        f"- 带风险指标样本: {veto['checked']}，违例（高风险却被 approve）: {veto['violation_count']}",
    ]
    if veto["violations"]:
        for v in veto["violations"]:
            lines.append(
                f"  - {v['timestamp']} trace={v['trace_id'][:8]} 回撤={v['max_drawdown']} 波动={v['volatility']}"
            )
    lines += [
        "",
        "## 否决理由完整",
        "",
        f"- checked {reason['checked']}，缺失理由 {reason['missing_count']}",
    ]
    for m in reason["missing"][:10]:
        lines.append(f"  - {m['timestamp']} trace={m['trace_id'][:8]} decision={m['decision']}")
    lines += [
        "",
        "> 分布不设占比下限（风控否决是职责所需）；防漂移以趋势记录为准。",
        "",
    ]
    return "\n".join(lines)


def run_offline(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """离线入口：纯函数路径（测试/CI 用），返回结构化结果。"""
    samples, parse_fail = extract_samples(traces)
    return {
        "samples": samples,
        "parse_fail": parse_fail,
        "aggregate": aggregate(samples),
        "veto_recall": veto_recall(samples),
        "reason_complete": reason_complete(samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FM 决策分布与质量度量")
    parser.add_argument(
        "--traces", type=Path, help="外部 trace JSON 列表文件（覆盖时不以 Langfuse 拉取）"
    )
    parser.add_argument("--out", type=Path, default=Path("reports/fm-decision-report.md"))
    args = parser.parse_args()

    if args.traces:
        traces: list[dict[str, Any]] = json.loads(args.traces.read_text(encoding="utf-8"))
    elif _fetch_fund_manager_traces is not None:
        traces = _fetch_fund_manager_traces()
    else:
        parser.error("未提供 --traces 且 run 模块不可导入（Langfuse 拉取不可用）")

    result = run_offline(traces)
    report = render_report(
        result["aggregate"], result["veto_recall"], result["reason_complete"], result["parse_fail"]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
