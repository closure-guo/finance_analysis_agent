"""确定性引用校验器 — 纯 Python 实现，不调 LLM，可进 CI。

参考 ADR-0011 和 FinGround (arXiv:2604.23588) 六类分类法。
复用 metrics/ 纯函数对 Agent 产出的 Claim 进行重算比对。
"""

from __future__ import annotations

import re
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


# ── claim 内部一致性（harden-citation-semantic-coverage）──

_NUMBER_PATTERN = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|％|亿|万|元)?")
_UNIT_SCALE = {"亿": 1e8, "万": 1e4, "元": 1.0, "%": 1.0, "％": 1.0, "": 1.0}

_NEGATIVE_WORDS = ("负增长", "下降", "下滑", "下跌", "回落", "走低", "减少", "降低", "恶化", "走弱")
_POSITIVE_WORDS = ("增长", "上升", "上涨", "提升", "提高", "改善", "走高", "回升", "向好")
_NEGATION_PREFIXES = ("负", "未", "无", "不")


def _extract_numbers(text: str) -> list[float]:
    """从自由文本提取数值（去千分位，亿/万缩放为原始单位，% 取面值）。

    仅返回单位缩放后的值（"0.68亿" → 6.8e7）。回声匹配需要同时比对面值时
    用 `_extract_number_candidates`，本函数签名/口径被 TestExtractNumbers 钉死，
    不得改动。
    """
    out: list[float] = []
    for m in _NUMBER_PATTERN.finditer(text):
        token = m.group(0)
        unit = token[-1] if token and token[-1] in _UNIT_SCALE else ""
        digits = token[:-1] if unit else token
        try:
            out.append(float(digits.replace(",", "").strip()) * _UNIT_SCALE[unit])
        except ValueError:
            continue
    return out


def _extract_number_candidates(text: str) -> list[float]:
    """回声匹配候选数值：对每个单位后缀 token 同时产出面值与缩放值。

    `_extract_numbers` 只返回缩放值（"0.68亿" → 6.8e7），但 claim 的
    stated_value 常以亿元/万元面值申报（stated=0.68），缩放候选经
    {1,100,0.01,1e4,1e8} 缩放集永远无法还原面值 → 误报。本函数对单位后缀
    token 额外补一份面值（"0.68亿" → 0.68 与 6.8e7 并列），纯数字 token
    只产面值一份。% / 元 单位缩放为 1.0，面值与缩放值相等（重复无副作用）。
    """
    out: list[float] = []
    for m in _NUMBER_PATTERN.finditer(text):
        token = m.group(0)
        unit = token[-1] if token and token[-1] in _UNIT_SCALE else ""
        digits = token[:-1] if unit else token
        try:
            face = float(digits.replace(",", "").strip())
        except ValueError:
            continue
        out.append(face)
        if unit:
            out.append(face * _UNIT_SCALE[unit])
    return out


def value_close(a: float, b: float) -> bool:
    """容差比对（max(0.01, 0.5%)，与数值型校验同族，允许双向不对称）。"""
    return abs(a - b) < max(0.01, 0.005 * max(abs(a), abs(b)))


def _check_internal_echo(claim: Claim) -> CitationResult | None:
    """数值回声：interpretation 含数值但无一与 stated_value 匹配 → FAIL。

    符号不敏感（abs 比对）：中文财务表述惯用「下降 5.2%」（幅度 + 方向词）
    而非「-5.2%」，符号一致性由方向词核对承担，回声只抓幅度两张皮。
    """
    try:
        stated = float(claim.stated_value)
    except (TypeError, ValueError):
        return None  # 非数值 stated（比较方向等）不适用回声检查
    candidates = _extract_number_candidates(claim.interpretation or "")
    if not candidates:
        return None  # 定性表述不强制回声（召回由正文覆盖率普查承担）
    for cand in candidates:
        for scale in (1.0, 100.0, 0.01, 1e4, 1e8):
            if value_close(abs(stated), abs(cand) * scale):
                return None
    return CitationResult(status="FAIL", claim=claim, bucket="internal_inconsistency")


def _direction_hits(text: str, words: tuple[str, ...]) -> list[int]:
    """方向词命中位置；排除紧邻否定前缀的「增长」类命中（负增长 ≠ 增长）。"""
    hits: list[int] = []
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            if w in _POSITIVE_WORDS and i > 0 and text[i - 1] in _NEGATION_PREFIXES:
                start = i + len(w)
                continue
            hits.append(i)
            start = i + len(w)
    return hits


def _is_growth_claim(claim: Claim) -> bool:
    """增长类 claim 判定（方向词核对适用面）。

    收敛口径（防误报）：root == "growth_rates"，或 root == "quarterly_trend"
    且系列段（parts[1]，去掉尾部 `[N]` 括号后）为 "yoy"/"qoq"。剔除原先
    「同比/环比/增速 in field_ref」子串判定——该子串误伤 macro 级 claim
    （macro_indicators.cpi.<idx>.全国-同比增长 引用的是 yoy RATE LEVEL，
    其 interpretation 对走势的评述（「回落」描述动能而非否定正值）不该判 FAIL）。
    """
    parts = claim.field_ref.split(".")
    root = parts[0] if parts else ""
    if root == "growth_rates":
        return True
    if root == "quarterly_trend" and len(parts) >= 2:
        series = re.sub(r"\[(-?\d+)\]$", "", parts[1])
        return series in ("yoy", "qoq")
    return False


def _check_direction_words(claim: Claim, base: CitationResult) -> CitationResult | None:
    """方向词核对（仅值级 PASS 时）：方向词与比较方向/增长符号矛盾 → FAIL。

    适用面收敛（v1 防误报）：comparative 全量；numerical/computational 仅
    growth_rates 根键或 quarterly_trend 的 yoy/qoq 系列增长类 claim。
    正负向词同时出现或均不出现 → 跳过（不赌复杂句语义）。
    """
    text = claim.interpretation or ""
    pos = bool(_direction_hits(text, _POSITIVE_WORDS))
    neg = bool(_direction_hits(text, _NEGATIVE_WORDS))
    if pos == neg:
        return None
    expect_positive: bool | None = None
    if claim.claim_type == "comparative":
        if claim.stated_value == "greater_than":
            expect_positive = True
        elif claim.stated_value == "less_than":
            expect_positive = False
    else:
        if _is_growth_claim(claim):
            try:
                expect_positive = float(claim.stated_value) > 0
            except (TypeError, ValueError):
                return None
    if expect_positive is None:
        return None
    if expect_positive and neg:
        return CitationResult(status="FAIL", claim=claim, bucket="internal_inconsistency")
    if not expect_positive and pos:
        return CitationResult(status="FAIL", claim=claim, bucket="internal_inconsistency")
    return None


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
    """data/mixed 数值族 claim 的完整校验链：术语 → 期次 → 内部回声 → 值级 → 方向词。

    首个 FAIL 短路；术语/期次缺省或不可解析计覆盖缺口（D5 显式降级）。
    方向词检查只在值级 PASS 上执行（值级 FAIL 已由重试反馈携带真值）。
    """
    term_fail = _check_metric_term(claim)
    if term_fail is not None:
        return term_fail
    period_fail, period_gap = _check_period(claim, state)
    if period_fail is not None:
        return period_fail
    echo_fail = _check_internal_echo(claim)
    if echo_fail is not None:
        return echo_fail
    result = value_fn(claim, state)
    if result.status == "PASS":
        direction_fail = _check_direction_words(claim, result)
        if direction_fail is not None:
            return direction_fail
    gap = period_gap or not (claim.metric_name or "").strip() or not (claim.period or "").strip()
    if gap:
        result.coverage_gap = True
    return result
