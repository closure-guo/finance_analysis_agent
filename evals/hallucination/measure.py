#!/usr/bin/env python
"""幻觉率度量 v1（add-hallucination-rate-metric）：数值型 claim 抽取 + 证据校验。

v1 范围（2026-09-04 决策）：数值型事实 claim（价格/涨跌幅/财务指标/市值）用
规则抽取、对行情与财务数据进行离线校验（supported/contradicted/unverifiable）——
无需 LLM 余额。事实型 claim（事件/日期/主体）抽取需 LLM，标记后续增量，v1 不
纳入（避免无样本校验的猜测性指标）。

幻觉率 = contradicted / 可验证 claim 总数（supported+contradicted）；
unverifiable 单列不进分子（合理推断/数据源缺失不惩罚）。

用法:
    uv run python evals/hallucination/measure.py --report path/to/report.md \\
        [--data path/to/data.json] [--out reports/hallucination-report.md]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# 数值型 claim 抽取规则（type → 正则；捕获组为数值）
NUMERIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("price", re.compile(r"(\d+(?:\.\d+)?)\s*元")),
    ("pct", re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")),
    ("cap_billion", re.compile(r"(\d+(?:\.\d+)?)\s*亿")),
    ("pe", re.compile(r"(?:PE|市盈率)\s*[=:]?\s*(\d+(?:\.\d+)?)")),
    ("pb", re.compile(r"(?:PB|市净率)\s*[=:]?\s*(\d+(?:\.\d+)?)")),
    ("roe", re.compile(r"(?:ROE|净资产收益率)\s*[为是:=]?\s*([+-]?\d+(?:\.\d+)?)\s*%")),
)

# 校验容差（按类型；比例型用相对容差，点数型用绝对容差）
TOLERANCES: dict[str, tuple[str, float]] = {
    "price": ("relative", 0.02),  # ±2%
    "pct": ("absolute", 0.5),  # ±0.5 个百分点
    "cap_billion": ("relative", 0.10),  # ±10%
    "pe": ("absolute", 1.0),
    "pb": ("absolute", 0.5),
    "roe": ("absolute", 1.0),  # ±1 个百分点
}


@dataclass
class Claim:
    type: str
    value: float
    raw: str
    index: int


@dataclass
class Verdict:
    claim: Claim
    status: str  # supported / contradicted / unverifiable
    expected: float | None = None


def extract_claims(report_text: str) -> list[Claim]:
    """规则抽取数值型 claim；同型重复值保留（每条独立校验）。"""
    claims: list[Claim] = []
    for ctype, pattern in NUMERIC_PATTERNS:
        for idx, m in enumerate(pattern.finditer(report_text or "")):
            try:
                value = float(m.group(1))
            except ValueError:
                continue
            claims.append(
                Claim(
                    type=ctype,
                    value=value,
                    raw=m.group(0),
                    index=idx,
                )
            )
    return claims


def _in_tolerance(ctype: str, actual: float, expected: float) -> bool:
    kind, tol = TOLERANCES.get(ctype, ("absolute", 0.5))
    if kind == "relative":
        return abs(actual - expected) <= tol * max(abs(expected), 1e-9)
    return abs(actual - expected) <= tol


def verify_claims(
    claims: list[Claim],
    data_map: dict[str, float],
) -> list[Verdict]:
    """对照 data_map 校验：缺数据源 → unverifiable；超容差 → contradicted。"""
    verdicts: list[Verdict] = []
    for c in claims:
        expected = data_map.get(c.type)
        if expected is None:
            verdicts.append(Verdict(claim=c, status="unverifiable"))
            continue
        if _in_tolerance(c.type, c.value, expected):
            verdicts.append(Verdict(claim=c, status="supported", expected=expected))
        else:
            verdicts.append(Verdict(claim=c, status="contradicted", expected=expected))
    return verdicts


@dataclass
class HallucinationResult:
    claims: list[Claim] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    contradicted: int = 0
    countable: int = 0
    unverifiable: int = 0
    rate: float | None = None


def hallucination_rate(verdicts: list[Verdict]) -> HallucinationResult:
    result = HallucinationResult(verdicts=verdicts)
    result.claims = [v.claim for v in verdicts]
    for v in verdicts:
        if v.status == "contradicted":
            result.contradicted += 1
        if v.status in ("supported", "contradicted"):
            result.countable += 1
        if v.status == "unverifiable":
            result.unverifiable += 1
    result.rate = round(result.contradicted / result.countable, 4) if result.countable else None
    return result


def render_report(result: HallucinationResult) -> str:
    lines = [
        "# 幻觉率报告（数值型 claim v1）",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- claim 总数: {len(result.claims)}（可验证 {result.countable} / 不可验证 {result.unverifiable}）",
        f"- 幻觉率: {f'{result.rate:.2%}' if result.rate is not None else '—'}（contradicted {result.contradicted} / 可验证 {result.countable}）",
        "",
        "## 被证伪 claim（contradicted）",
        "",
    ]
    contradicted = [v for v in result.verdicts if v.status == "contradicted"]
    if not contradicted:
        lines.append("（无）")
    for v in contradicted[:10]:
        lines.append(
            f"- {v.claim.type}「{v.claim.raw}」（claim {v.claim.value} vs 实际 {v.expected}）"
        )
    lines += [
        "",
        "## 不可验证（unverifiable，单列不进分子）",
        "",
    ]
    unver = [v for v in result.verdicts if v.status == "unverifiable"]
    if not unver:
        lines.append("（无）")
    for v in unver[:10]:
        lines.append(f"- {v.claim.type}「{v.claim.raw}」")
    lines += ["", "> v1 仅数值型 claim；事实型 claim（事件/日期/主体）抽取需 LLM，属后续增量。", ""]
    return "\n".join(lines)


def run_offline(
    report_text: str,
    data_map: dict[str, float] | None = None,
) -> HallucinationResult:
    claims = extract_claims(report_text)
    verdicts = verify_claims(claims, data_map or {})
    return hallucination_rate(verdicts)


def main() -> None:
    parser = argparse.ArgumentParser(description="幻觉率度量（数值型 claim v1）")
    parser.add_argument("--report", type=Path, required=True, help="报告 markdown 路径")
    parser.add_argument("--data", type=Path, default=None, help="校验数据 JSON（{type: value}）")
    parser.add_argument("--out", type=Path, default=Path("reports/hallucination-report.md"))
    args = parser.parse_args()

    report_text = args.report.read_text(encoding="utf-8")
    data_map: dict[str, float] = {}
    if args.data and args.data.exists():
        data_map = json.loads(args.data.read_text(encoding="utf-8"))
    result = run_offline(report_text, data_map)
    text = render_report(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
