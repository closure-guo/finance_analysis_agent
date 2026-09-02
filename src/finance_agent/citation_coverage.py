"""正文数字普查（citation recall 的确定性近似，ALCE 对齐）。

口径（design D1，fixture 钉死）：
- 只普查带单位形态的数值：%/％/个百分点 → percent（面值）；亿/万/元 → amount
  （缩放为原始单位）；倍/x/X → multiple（面值）；修饰词（约/接近/左右…）剥离。
- 无单位裸数一律豁免 → 年份、编号（5 层/3 大）、指标参数（MA5/RSI14）、
  股票代码（600519）、日期段天然不计入；「N 期」不普查，「N 个百分点」按
  percent 计；评级刻度（AAA/85 分）无命中。
- 认领判定（refine-citation-coverage-v3 D1，issue #106 人工终裁）：
  - 普查容差独立为 2% 相对（下限 0.01），不再复用校验器 0.5%——普查是召回工具；
  - 方向词（下滑/下降/增长…）语境符号不敏感匹配；
  - 「超/低于/约/近」修饰按不等式/近似阈值匹配；
  - 模板/脚手架文本（仓位档位说明等）不计入普查。
- 覆盖率只监控告警，不进路由。
"""

from __future__ import annotations

import re
from typing import NamedTuple

from finance_agent.citation import value_close  # noqa: F401  兼容既有 import

CENSUS_TOL = 0.02  # 普查相对容差（v3：2%）；绝对值下限 0.01
CENSUS_INEQ_BAND = 0.20  # 不等式匹配邻域带：claim 须与「超/低于 X」的 X 量级接近（20%），
# 否则视为不同量级（防跨指标误认领，如 1400亿 被营收 1720.5亿 认领）

_CENSUS_RE = re.compile(
    r"(?P<num>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>个百分点|%|％|亿|万|元|倍|[xX])"
)
_UNIT_KIND = {
    "%": "percent",
    "％": "percent",
    "个百分点": "percent",
    "亿": "amount",
    "万": "amount",
    "元": "amount",
    "倍": "multiple",
    "x": "multiple",
    "X": "multiple",
}
_UNIT_SCALE = {"亿": 1e8, "万": 1e4}
# 「N 期」（窗口期数）豁免由正则天然实现：期不在 unit 枚举内；
# 「N 个百分点」属 percent 命中，不在此列

_CLAIM_SCALES = (1.0, 100.0, 0.01, 1e4, 1e8)

# v3 语境标记
_DIRECTION_WORDS = (
    "下滑",
    "下降",
    "增长",
    "上升",
    "减少",
    "增加",
    "回落",
    "下跌",
    "上涨",
    "走低",
    "走高",
    "下滑",
)
_INEQ_GE = ("超", "超过", "高于", "大于", "不低于", "达到")
_INEQ_LE = ("低于", "不足", "小于", "不高于")
_INEQ_APPROX = ("约", "近", "接近", "大约")
_SCAFFOLD_HINTS = ("档位", "仓位", "如总资金", "试探性", "决策语义", "position_size")
_CONTEXT_WINDOW = 20  # 方向词/修饰词探测窗口（字符）
_LOOKBACK = 8  # 不等式修饰词只看数字前的短窗口


class CensusNumber(NamedTuple):
    raw: str  # 原文片段（去空白，如 "10.39亿"），用于 unmatched 披露
    value: float
    kind: str  # percent | amount | multiple
    direction_neg: bool = False  # 邻近方向词 → 符号不敏感匹配
    inequality: str = ""  # "ge" / "le" / "approx"（"" = 等值匹配）


class CoverageReport(NamedTuple):
    coverage: float  # 已认领 / 普查总数；total=0 时 1.0（无数字即无黑数字）
    total: int
    matched: int
    unmatched: list[str]  # 未认领原文片段（稳定序）
    event_covered: list[str] = []  # v3：命中事件源的数值（不计 unmatched）


def _census_close(a: float, b: float) -> bool:
    """普查容差（2% 相对，0.01 绝对下限）。"""
    return abs(a - b) <= max(0.01, CENSUS_TOL * max(abs(a), abs(b)))


def _window(markdown: str, start: int, end: int) -> str:
    return markdown[max(0, start - _CONTEXT_WINDOW) : end + _CONTEXT_WINDOW]


def _classify_context(markdown: str, start: int, end: int) -> tuple[bool, str]:
    """返回 (direction_neg, inequality)。inequality 只看数字前短窗口。"""
    ctx = _window(markdown, start, end)
    direction = any(w in ctx for w in _DIRECTION_WORDS)
    before = markdown[max(0, start - _LOOKBACK) : start]
    ineq = ""
    if any(w in before for w in _INEQ_GE):
        ineq = "ge"
    elif any(w in before for w in _INEQ_LE):
        ineq = "le"
    elif any(w in before for w in _INEQ_APPROX):
        ineq = "approx"
    return direction, ineq


def extract_census_numbers(markdown: str) -> list[CensusNumber]:
    """从 markdown 提取带单位数值，按 (kind, value) 去重（保持首次出现序）。

    v3：脚手架/模板文本区间内的数值直接跳过（不计入普查总数）。
    """
    seen: set[tuple[str, float]] = set()
    out: list[CensusNumber] = []
    for m in _CENSUS_RE.finditer(markdown):
        start = m.start()
        # 日期段保护：紧邻前字符为 '-' 且本身是日期一部分（2026-08-28 的 28）——
        # 无单位不命中本正则，无需处理；此处防御「-08」类碎片
        if start > 0 and markdown[start - 1] == "-" and not m.group("num").startswith("-"):
            continue
        ctx = _window(markdown, start, m.end())
        if any(h in ctx for h in _SCAFFOLD_HINTS):
            continue  # 脚手架/模板文本：不计入普查
        unit = m.group("unit")
        digits = m.group("num").replace(",", "")
        try:
            value = float(digits) * _UNIT_SCALE.get(unit, 1.0)
        except ValueError:
            continue
        kind = _UNIT_KIND[unit]
        key = (kind, round(value, 6))
        if key in seen:
            continue
        seen.add(key)
        direction, ineq = _classify_context(markdown, start, m.end())
        raw = f"{m.group('num')}{unit}".replace(" ", "")
        out.append(
            CensusNumber(raw=raw, value=value, kind=kind, direction_neg=direction, inequality=ineq)
        )
    return out


def _natural_targets(n: CensusNumber, stated: list[float]) -> list[float]:
    """每条 stated 取与 n.value 最接近的缩放（自然面值），去重。"""
    out: list[float] = []
    for sv in stated:
        cands = [sv * scale for scale in _CLAIM_SCALES if sv * scale]
        if not cands:
            continue
        best = min(cands, key=lambda t: abs(abs(t) - abs(n.value)))
        if best not in out:
            out.append(best)
    return out


def _matches(n: CensusNumber, stated: list[float]) -> bool:
    """单数值 vs stated 集合匹配（等值/方向词/不等式/近似）。"""
    targets = _natural_targets(n, stated)
    if not targets:
        return False
    if n.inequality == "ge":
        # 「超 X」：claim 的 X 面值须与 n.value 量级接近（邻域带内）且满足 ≥
        return any(
            abs(t - n.value) <= CENSUS_INEQ_BAND * abs(n.value) and t >= n.value for t in targets
        )
    if n.inequality == "le":
        return any(
            abs(t - n.value) <= CENSUS_INEQ_BAND * abs(n.value) and t <= n.value for t in targets
        )
    if n.inequality == "approx":
        return any(_census_close(n.value, t) for t in targets)
    if n.direction_neg:
        return any(_census_close(abs(n.value), abs(t)) for t in targets)
    return any(_census_close(n.value, t) for t in targets)


def compute_coverage(
    markdown: str,
    stated_values: list[float],
    event_values: list[float] | None = None,
) -> CoverageReport:
    """普查 markdown，逐一与 claim stated_value 集合匹配，产出覆盖率。

    event_values：state 事件源（key_events/news）中出现的数值，命中即标记
    event_covered（v3 D5），不计 unmatched。
    """
    numbers = extract_census_numbers(markdown)
    unmatched: list[str] = []
    event_covered: list[str] = []
    for n in numbers:
        if event_values and any(_census_close(n.value, ev) for ev in event_values):
            event_covered.append(n.raw)
            continue
        if not _matches(n, stated_values):
            unmatched.append(n.raw)
    total = len(numbers)
    matched = total - len(unmatched)
    coverage = matched / total if total else 1.0
    return CoverageReport(
        coverage=coverage,
        total=total,
        matched=matched,
        unmatched=unmatched,
        event_covered=event_covered,
    )
