"""确定性引用校验器 — 纯 Python 实现，不调 LLM，可进 CI。

参考 ADR-0011 和 FinGround (arXiv:2604.23588) 六类分类法。
复用 metrics/ 纯函数对 Agent 产出的 Claim 进行重算比对。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, TypeGuard

from pydantic import BaseModel

from finance_agent.metric_vocab import (
    canonical_metric,
    field_ref_metric_segments,
    field_ref_period_segment,
    normalize_period,
    period_matches,
)
from finance_agent.metrics.cashflow import calc_cashflow
from finance_agent.metrics.dupont import calc_dupont
from finance_agent.metrics.efficiency import calc_efficiency
from finance_agent.metrics.profitability import calc_profitability
from finance_agent.metrics.risk import calc_risk
from finance_agent.metrics.solvency import calc_solvency
from finance_agent.metrics.technical import calc_technical

if TYPE_CHECKING:
    import pandas as pd


class Claim(BaseModel):
    """原子声明 — Agent 报告中的单个可验证数据点。"""

    claim_type: Literal[
        "numerical",
        "temporal",
        "entity",
        "comparative",
        "regulatory",
        "computational",
    ]
    source_type: Literal["data", "event", "llm_inference", "mixed"]
    field_ref: str  # state 字段路径，如 "solvency_metrics.资产负债率.2024"
    stated_value: float | str
    interpretation: str
    field_ref_b: str | None = None  # 比较型 claim 的第二个值路径
    # harden-citation-semantic-coverage：术语/期次申报。None = 未申报（旧格式），
    # 校验器跳过对应检查并计覆盖缺口（显式降级，不静默 PASS）。
    metric_name: str | None = None  # 指标枚举（中文规范键或别名，见 metric_vocab）
    period: str | None = None  # 期次（2024 / 2025Q2 / 2026-08-28 / 2026-07）


class CitationResult(BaseModel):
    """单条 Claim 的校验结果。"""

    status: Literal["PASS", "FAIL", "UNVERIFIABLE"]
    claim: Claim
    ground_truth: float | str | None = None
    delta: float | None = None
    coverage_gap: bool = False  # 覆盖缺口（未注册根键 / 未申报术语期次）
    # FAIL 分桶（harden-citation-semantic-coverage）：value_mismatch=值级（gt 存在且
    # 超容差，定向重试）；path_unresolvable=路径/事件不可解析；semantic_*=术语/期次
    # 张冠李戴；internal_inconsistency=stated 与 interpretation 两张皮/方向矛盾。
    bucket: (
        Literal[
            "value_mismatch",
            "path_unresolvable",
            "semantic_term_mismatch",
            "semantic_period_mismatch",
            "internal_inconsistency",
        ]
        | None
    ) = None


class CitationReport(BaseModel):
    """批量校验汇总报告。"""

    results: list[CitationResult]
    total: int = 0
    passed: int = 0
    failed: int = 0
    unverifiable: int = 0
    coverage_gaps: int = 0
    all_passed: bool = False

    @classmethod
    def from_results(cls, results: list[CitationResult]) -> CitationReport:
        """从校验结果列表构建汇总报告。"""
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        unverifiable = sum(1 for r in results if r.status == "UNVERIFIABLE")
        return cls(
            results=results,
            total=len(results),
            passed=passed,
            failed=failed,
            unverifiable=unverifiable,
            coverage_gaps=sum(1 for r in results if r.coverage_gap),
            all_passed=failed == 0,
        )


def _expand_brackets(field_ref: str) -> list[str]:
    """展开 `[N]` 括号索引：`quarterly_trend.yoy[1]` → ["quarterly_trend", "yoy", "1"]。

    fix-citation-contract-diseases 修 B：LLM 按数组语义书写下标，resolver
    统一展开为路径段，负索引（-N）原样保留（list 负下标 = 倒数第 N 个）。
    """
    import re

    parts: list[str] = []
    pattern = re.compile(r"^(.*?)\[(-?\d+)\]$")
    for seg in field_ref.split("."):
        m = pattern.match(seg)
        if m:
            base, idx = m.group(1), m.group(2)
            if base:
                parts.append(base)
            parts.append(idx)
        else:
            parts.append(seg)
    return parts


def _is_dataframe(obj: object) -> TypeGuard[pd.DataFrame]:
    """鸭子判定 DataFrame（columns + iloc）；TypeGuard 供 mypy 收窄，运行时不导入 pandas。"""
    return hasattr(obj, "columns") and hasattr(obj, "iloc")


def _resolve_field_ref(field_ref: str, state: dict) -> object | None:
    """按 "." 分割路径（含 `[N]` 括号展开），逐层遍历 state dict / list / DataFrame。

    - 负索引（修 A）：list[-N] = 倒数第 N 个（-1 = 最新一期），与序列长度及
      context 裁剪窗口解耦；
    - DataFrame（修 B）：期望「行键.列名」两段——行键按任意列单元格值匹配
      （如 报告日 20251231），列名须为真实列，如
      income_statement.20251231.营业总收入；
    - fetch 守卫结构兼容：dict 形如 {"records": [...], "as_of_date", "freshness"}
      时，若当前 part 不是该 dict 的键，先自动下钻 records 再解析，保持
      field_ref 语义（macro_indicators.cpi.0.<列>）不变。
    """
    parts = _expand_brackets(field_ref)
    current: object = state
    i = 0
    while i < len(parts):
        part = parts[i]
        if isinstance(current, dict) and "records" in current and part not in current:
            current = current["records"]
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif _is_dataframe(current):
            if i + 1 >= len(parts):
                return None
            col_name = parts[i + 1]
            if col_name not in current.columns:
                return None
            mask = None
            for col in current.columns:
                mask = current[col].astype(str) == part
                if mask.any():
                    break
            if mask is None or not mask.any():
                return None
            current = current[mask].iloc[0][col_name]
            i += 2
            continue
        else:
            return None
        i += 1
    return current


# ── 计算型 claim 重算注册表 ──
# field_ref 根键 → 从 state 原始数据重算的函数。
# 覆盖 metrics/ 全部纯函数指标族；未注册根键 → UNVERIFIABLE + coverage_gap 计数。
_COMPUTATIONAL_RECALC: dict[str, Callable[[dict], dict]] = {
    "dupont_tree": lambda s: calc_dupont(s["balance_sheet"], s["income_statement"]),
    "solvency_metrics": lambda s: calc_solvency(
        s["balance_sheet"], s["income_statement"], s.get("financial_indicators")
    ),
    "profitability_metrics": lambda s: calc_profitability(
        s["balance_sheet"], s["income_statement"], s.get("financial_indicators")
    ),
    "efficiency_metrics": lambda s: calc_efficiency(
        s["balance_sheet"], s["income_statement"], s.get("financial_indicators")
    ),
    "cashflow_metrics": lambda s: calc_cashflow(
        s["balance_sheet"], s["income_statement"], s["cash_flow_statement"]
    ),
    "technical_indicators": lambda s: calc_technical(s["kline"]),
    "risk_metrics": lambda s: calc_risk(s["kline"], s.get("benchmark_kline")),
}


def _verify_computational(claim: Claim, state: dict) -> CitationResult:
    """计算型 claim：从原始数据重算指标，用相对容差 0.5% 比对。"""
    parts = claim.field_ref.split(".")
    root = parts[0]
    sub_path = parts[1:]

    recalc_fn = _COMPUTATIONAL_RECALC.get(root)
    if recalc_fn is None:
        return CitationResult(status="UNVERIFIABLE", claim=claim, coverage_gap=True)

    try:
        recalculated = recalc_fn(state)
    except (KeyError, TypeError):
        return CitationResult(status="UNVERIFIABLE", claim=claim)

    # 从重算结果中按 sub_path 取值（dict 键 + list 序号，与 _resolve_field_ref 语义一致）
    current: object = recalculated
    for part in sub_path:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return CitationResult(status="UNVERIFIABLE", claim=claim)
        else:
            return CitationResult(status="UNVERIFIABLE", claim=claim)
        if current is None:
            return CitationResult(
                status="FAIL",
                claim=claim,
                ground_truth=None,
                delta=None,
                bucket="path_unresolvable",
            )

    if not isinstance(current, int | float | str):
        return CitationResult(
            status="FAIL",
            claim=claim,
            ground_truth=None,
            delta=None,
            bucket="path_unresolvable",
        )
    try:
        ground_truth = float(current)
        stated = float(claim.stated_value)
    except (TypeError, ValueError):
        return CitationResult(
            status="FAIL",
            claim=claim,
            ground_truth=None,
            delta=None,
            bucket="path_unresolvable",
        )
    delta = abs(ground_truth - stated)

    # 相对容差 0.5%（FinGround 标准）
    passed = delta < 0.01 if ground_truth == 0 else delta / abs(ground_truth) < 0.005

    return CitationResult(
        status="PASS" if passed else "FAIL",
        claim=claim,
        ground_truth=ground_truth,
        delta=delta,
        bucket=None if passed else "value_mismatch",
    )


def _verify_numerical(claim: Claim, state: dict) -> CitationResult:
    """数值型 claim：直接读 state 字段，绝对容差 0.01 比对。

    field_ref 解析结果非数值（dict/list 等，LLM 偶发指到容器节点）时按
    FAIL 处理而非抛 TypeError 炸管线（baseline-v2 r3 回归）。
    """
    ground_truth = _resolve_field_ref(claim.field_ref, state)
    if not isinstance(ground_truth, int | float | str):
        return CitationResult(
            status="FAIL",
            claim=claim,
            ground_truth=None,
            delta=None,
            bucket="path_unresolvable",
        )
    try:
        gt_float = float(ground_truth)
        sv_float = float(claim.stated_value)
    except (TypeError, ValueError):
        return CitationResult(
            status="FAIL",
            claim=claim,
            ground_truth=None,
            delta=None,
            bucket="path_unresolvable",
        )
    delta = abs(gt_float - sv_float)
    # fix-citation-contract-diseases 修 C：|delta|<0.01 或相对误差<0.5%
    # （与计算型容差对齐；绝对 0.01 对亿元级数值是假阴性——LLM 须精确到分才过）
    tol = max(0.01, abs(gt_float) * 0.005)
    status: Literal["PASS", "FAIL"] = "PASS" if delta < tol else "FAIL"
    return CitationResult(
        status=status,
        claim=claim,
        ground_truth=gt_float,
        delta=delta,
        bucket=None if status == "PASS" else "value_mismatch",
    )


def _verify_comparative(claim: Claim, state: dict) -> CitationResult:
    """比较型 claim：验证两侧数值 + 比较方向。"""
    val_a = _resolve_field_ref(claim.field_ref, state)
    val_b = _resolve_field_ref(claim.field_ref_b, state) if claim.field_ref_b else None
    if not isinstance(val_a, int | float | str) or not isinstance(val_b, int | float | str):
        return CitationResult(
            status="FAIL", claim=claim, ground_truth=None, bucket="path_unresolvable"
        )

    try:
        a = float(val_a)
        b = float(val_b)
    except (TypeError, ValueError):
        return CitationResult(
            status="FAIL", claim=claim, ground_truth=None, bucket="path_unresolvable"
        )
    delta = abs(a - b)
    direction = str(claim.stated_value)

    if direction == "greater_than":
        passed = a > b
    elif direction == "less_than":
        passed = a < b
    elif direction == "equal_to":
        passed = delta < 0.01
    else:
        return CitationResult(status="UNVERIFIABLE", claim=claim)

    status: Literal["PASS", "FAIL"] = "PASS" if passed else "FAIL"
    return CitationResult(
        status=status,
        claim=claim,
        ground_truth=a,
        delta=delta,
        bucket=None if passed else "value_mismatch",
    )


def _verify_event(claim: Claim, state: dict) -> CitationResult:
    """事件型 claim：验证引用的事件存在于 key_events。"""
    key_events = state.get("key_events", [])
    if not isinstance(key_events, list):
        return CitationResult(
            status="FAIL", claim=claim, ground_truth=None, bucket="path_unresolvable"
        )

    event_title = claim.field_ref
    for event in key_events:
        if isinstance(event, dict) and event.get("title") == event_title:
            # 事件存在，可选校验日期
            if claim.stated_value and event.get("date"):
                if str(event["date"]) == str(claim.stated_value):
                    return CitationResult(status="PASS", claim=claim, ground_truth=event["date"])
                return CitationResult(
                    status="FAIL",
                    claim=claim,
                    ground_truth=event["date"],
                    bucket="value_mismatch",
                )
            return CitationResult(status="PASS", claim=claim)

    return CitationResult(status="FAIL", claim=claim, ground_truth=None, bucket="path_unresolvable")


# ── 语义层检查（harden-citation-semantic-coverage）──


def _check_metric_term(claim: Claim) -> CitationResult | None:
    """术语一致性：metric_name 规范键须命中 field_ref 指标段。不一致/词表外 → FAIL。"""
    name = (claim.metric_name or "").strip()
    if not name:
        return None
    canonical = canonical_metric(name)
    segments = field_ref_metric_segments(claim.field_ref)
    seg_keys = {(canonical_metric(s) or s) for s in segments}
    if canonical is None or canonical not in seg_keys:
        return CitationResult(status="FAIL", claim=claim, bucket="semantic_term_mismatch")
    return None


def _resolve_index_period(field_ref: str, state: dict) -> str | None:
    """索引锚定引用（无显式期次段）从 state 解析实际期次标签；解析不出返回 None。

    technical_indicators.X.Y.<idx> → kline 日期列同索引（序列与 kline 等长、升序）；
    macro_indicators.<key>.<idx>.<列> → records[idx]["月份"]
        （4 段式索引在 parts[2]，亦接受键上括号 macro_indicators.<key>[<idx>].<列>；
        T3 修复：旧实现只看 parts[-1]，macro 期次恒解析不出、静默降级为缺口）；
    quarterly_trend.<key>[<idx>] → quarters[idx]。
    """
    import re as _re

    parts = field_ref.split(".")
    root = parts[0] if parts else ""
    idx: int | None = None
    try:
        if root == "macro_indicators":
            if len(parts) < 3:
                return None
            key = parts[1]
            bracket = _re.search(r"\[(-?\d+)\]$", key)
            if bracket:
                idx = int(bracket.group(1))
                key = key[: bracket.start()]
            elif _re.match(r"^-?\d+$", parts[2]):
                idx = int(parts[2])
            if idx is None:
                return None
            recs = state["macro_indicators"][key]
            if isinstance(recs, dict):
                recs = recs.get("records") or []
            return str(recs[idx].get("月份", "")) or None

        m = _re.match(r"^-?\d+$", parts[-1]) if parts else None
        bracket = _re.search(r"\[(-?\d+)\]$", parts[-1]) if parts else None
        if bracket:
            idx = int(bracket.group(1))
        elif m and root in {"technical_indicators", "quarterly_trend"}:
            idx = int(parts[-1])
        if idx is None:
            return None
        if root == "technical_indicators":
            dates = state["kline"]["日期"]
            return str(dates.iloc[idx])
        if root == "quarterly_trend":
            return str(state["quarterly_trend"]["quarters"][idx]) or None
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    return None


def _check_period(claim: Claim, state: dict) -> tuple[CitationResult | None, bool]:
    """期次一致性。返回 (FAIL 结果或 None, 是否覆盖缺口)。"""
    declared = (claim.period or "").strip()
    if not declared:
        return None, False
    if normalize_period(declared) is None:
        return None, True  # 期次表述无法归一化 → 缺口，不误伤
    actual = field_ref_period_segment(claim.field_ref)
    if actual is None:
        actual = _resolve_index_period(claim.field_ref, state)
        if actual is None:
            return None, True  # 索引期次解析不出 → 缺口
    if period_matches(declared, actual):
        return None, False
    return (
        CitationResult(status="FAIL", claim=claim, bucket="semantic_period_mismatch"),
        False,
    )


def verify_claims(claims: list[Claim], state: dict) -> list[CitationResult]:
    """校验所有 Claim，返回逐条结果。"""
    results: list[CitationResult] = []
    for claim in claims:
        if claim.source_type == "llm_inference":
            results.append(CitationResult(status="UNVERIFIABLE", claim=claim))
        elif claim.source_type == "event":
            results.append(_verify_event(claim, state))
        elif claim.claim_type == "numerical":
            results.append(_verify_data_claim(claim, state, _verify_numerical))
        elif claim.claim_type == "computational":
            results.append(_verify_data_claim(claim, state, _verify_computational))
        elif claim.claim_type == "comparative":
            results.append(_verify_data_claim(claim, state, _verify_comparative))
        else:
            results.append(CitationResult(status="UNVERIFIABLE", claim=claim))
    return results


def _verify_data_claim(
    claim: Claim,
    state: dict,
    value_fn: Callable[[Claim, dict], CitationResult],
) -> CitationResult:
    """data/mixed 数值族 claim 的完整校验链：术语 → 期次 → 值级。

    首个 FAIL 短路（桶即首个失败因）；术语/期次缺省或不可解析计覆盖缺口
    （coverage_gap=True），不静默 PASS（D5）。
    """
    term_fail = _check_metric_term(claim)
    if term_fail is not None:
        return term_fail
    period_fail, period_gap = _check_period(claim, state)
    if period_fail is not None:
        return period_fail
    result = value_fn(claim, state)
    gap = period_gap or not (claim.metric_name or "").strip() or not (claim.period or "").strip()
    if gap:
        result.coverage_gap = True
    return result
