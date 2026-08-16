"""确定性引用校验器 — 纯 Python 实现，不调 LLM，可进 CI。

参考 ADR-0011 和 FinGround (arXiv:2604.23588) 六类分类法。
复用 metrics/ 纯函数对 Agent 产出的 Claim 进行重算比对。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from finance_agent.metrics.dupont import calc_dupont


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


class CitationResult(BaseModel):
    """单条 Claim 的校验结果。"""

    status: Literal["PASS", "FAIL", "UNVERIFIABLE"]
    claim: Claim
    ground_truth: float | str | None = None
    delta: float | None = None


class CitationReport(BaseModel):
    """批量校验汇总报告。"""

    results: list[CitationResult]
    total: int = 0
    passed: int = 0
    failed: int = 0
    unverifiable: int = 0
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
            all_passed=failed == 0,
        )


def _resolve_field_ref(field_ref: str, state: dict) -> object | None:
    """按 "." 分割路径，逐层遍历 state dict / list。"""
    current: object = state
    for part in field_ref.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


# ── 计算型 claim 重算注册表 ──
# field_ref 根键 → 从 state 原始数据重算的函数
_COMPUTATIONAL_RECALC: dict[str, Callable[[dict], dict]] = {
    "dupont_tree": lambda s: calc_dupont(s["balance_sheet"], s["income_statement"]),
}


def _verify_computational(claim: Claim, state: dict) -> CitationResult:
    """计算型 claim：从原始数据重算指标，用相对容差 0.5% 比对。"""
    parts = claim.field_ref.split(".")
    root = parts[0]
    sub_path = parts[1:]

    recalc_fn = _COMPUTATIONAL_RECALC.get(root)
    if recalc_fn is None:
        return CitationResult(status="UNVERIFIABLE", claim=claim)

    try:
        recalculated = recalc_fn(state)
    except (KeyError, TypeError):
        return CitationResult(status="UNVERIFIABLE", claim=claim)

    # 从重算结果中按 sub_path 取值
    current: object = recalculated
    for part in sub_path:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return CitationResult(status="UNVERIFIABLE", claim=claim)
        if current is None:
            return CitationResult(status="FAIL", claim=claim, ground_truth=None, delta=None)

    if not isinstance(current, int | float | str):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None, delta=None)
    try:
        ground_truth = float(current)
        stated = float(claim.stated_value)
    except (TypeError, ValueError):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None, delta=None)
    delta = abs(ground_truth - stated)

    # 相对容差 0.5%（FinGround 标准）
    passed = delta < 0.01 if ground_truth == 0 else delta / abs(ground_truth) < 0.005

    return CitationResult(
        status="PASS" if passed else "FAIL",
        claim=claim,
        ground_truth=ground_truth,
        delta=delta,
    )


def _verify_numerical(claim: Claim, state: dict) -> CitationResult:
    """数值型 claim：直接读 state 字段，绝对容差 0.01 比对。

    field_ref 解析结果非数值（dict/list 等，LLM 偶发指到容器节点）时按
    FAIL 处理而非抛 TypeError 炸管线（baseline-v2 r3 回归）。
    """
    ground_truth = _resolve_field_ref(claim.field_ref, state)
    if not isinstance(ground_truth, int | float | str):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None, delta=None)
    try:
        gt_float = float(ground_truth)
        sv_float = float(claim.stated_value)
    except (TypeError, ValueError):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None, delta=None)
    delta = abs(gt_float - sv_float)
    status: Literal["PASS", "FAIL"] = "PASS" if delta < 0.01 else "FAIL"
    return CitationResult(status=status, claim=claim, ground_truth=gt_float, delta=delta)


def _verify_comparative(claim: Claim, state: dict) -> CitationResult:
    """比较型 claim：验证两侧数值 + 比较方向。"""
    val_a = _resolve_field_ref(claim.field_ref, state)
    val_b = _resolve_field_ref(claim.field_ref_b, state) if claim.field_ref_b else None
    if not isinstance(val_a, int | float | str) or not isinstance(val_b, int | float | str):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None)

    try:
        a = float(val_a)
        b = float(val_b)
    except (TypeError, ValueError):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None)
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
    return CitationResult(status=status, claim=claim, ground_truth=a, delta=delta)


def _verify_event(claim: Claim, state: dict) -> CitationResult:
    """事件型 claim：验证引用的事件存在于 key_events。"""
    key_events = state.get("key_events", [])
    if not isinstance(key_events, list):
        return CitationResult(status="FAIL", claim=claim, ground_truth=None)

    event_title = claim.field_ref
    for event in key_events:
        if isinstance(event, dict) and event.get("title") == event_title:
            # 事件存在，可选校验日期
            if claim.stated_value and event.get("date"):
                if str(event["date"]) == str(claim.stated_value):
                    return CitationResult(status="PASS", claim=claim, ground_truth=event["date"])
                return CitationResult(status="FAIL", claim=claim, ground_truth=event["date"])
            return CitationResult(status="PASS", claim=claim)

    return CitationResult(status="FAIL", claim=claim, ground_truth=None)


def verify_claims(claims: list[Claim], state: dict) -> list[CitationResult]:
    """校验所有 Claim，返回逐条结果。"""
    results: list[CitationResult] = []
    for claim in claims:
        if claim.source_type == "llm_inference":
            results.append(CitationResult(status="UNVERIFIABLE", claim=claim))
        elif claim.source_type == "event":
            results.append(_verify_event(claim, state))
        elif claim.claim_type == "numerical":
            results.append(_verify_numerical(claim, state))
        elif claim.claim_type == "computational":
            results.append(_verify_computational(claim, state))
        elif claim.claim_type == "comparative":
            results.append(_verify_comparative(claim, state))
        else:
            results.append(CitationResult(status="UNVERIFIABLE", claim=claim))
    return results
