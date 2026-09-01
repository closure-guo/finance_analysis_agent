"""离线复判（offline re-judgment）：在无 state 时按当前契约重建校验器裁决。

背景（verifier-baseline-v1）：历史 claim 只收割到 Langfuse trace 的
``metadata.citation_report``（claim / verifier_status / ground_truth / delta），
管线 state 不落库。测量时无法重跑 ``verify_claims`` 的 field_ref 解析层，
只能对「裁决层」做离线复判：逐条按当前契约的容差语义与三态规则，用收割到的
(ground_truth, delta) 重建校验器裁决，与人工标签对比。

边界（诚实披露，不冒充解析层）：
- ground_truth 缺失（旧契约下词表/索引疾病样本，gt 不可得或为 None）→
  离线不可复判，返回 UNVERIFIABLE（由调用方计入 regression 子集单独披露）；
- 比较型 greater/less 需要 |a-b| 的符号，delta 不含符号 → 离线不可复判；
- 事件型 gt 缺失（事件是否存在不可知）→ 离线不可复判。

防漂移：本模块公式与 citation.py 裁决函数逐条对齐，并用
tests/evals/claim_benchmark/test_rejudge.py 的钉死测试锁定——
若 citation.py 容差语义变更，钉死测试失败告警镜像漂移。

**不修改 citation.py**（红线：契约语义属上一 delta 冻结范围）。
"""

from __future__ import annotations

from typing import Literal

Status = Literal["PASS", "FAIL", "UNVERIFIABLE"]

# 与 citation.py 对齐的容差常量（修 C 双条件）
ABS_TOL = 0.01  # 绝对容差：|delta| < 0.01
REL_TOL = 0.005  # 相对容差：|delta| / |gt| < 0.5%

# 模糊措辞词表（hedged 子集识别；与「约/接近」口径一致）
HEDGE_WORDS = ("约", "接近", "左右", "大约", "近似", "近", "约等于")


def rejudge_claim(claim: dict, ground_truth: object | None, delta: object | None) -> Status:
    """按当前契约重建单条 claim 的校验器裁决。

    Args:
        claim: 收割到的 claim dict（含 claim_type / source_type / stated_value）。
        ground_truth: trace 记录的解析值（None = 解析层不可得）。
        delta: trace 记录的 |ground_truth - stated|（事件型为 None）。

    Returns:
        PASS / FAIL / UNVERIFIABLE（UNVERIFIABLE = 离线不可复判，非校验器裁决）。
    """
    source_type = claim.get("source_type")
    if source_type == "llm_inference":
        return "UNVERIFIABLE"

    semantic = _rejudge_semantic(claim)
    if semantic is not None:
        return semantic

    claim_type = claim.get("claim_type")

    if claim_type == "event":
        return _rejudge_event(claim, ground_truth)

    gt, dv = _coerce_numeric(ground_truth), _coerce_numeric(delta)

    if claim_type == "numerical":
        if gt is None:
            return "UNVERIFIABLE"
        # 数值型：|delta| < 0.01 或 相对误差 < 0.5%（修 C，与计算型对齐）
        tol = max(ABS_TOL, abs(gt) * REL_TOL)
        return "PASS" if dv is not None and dv < tol else "FAIL"

    if claim_type == "computational":
        if gt is None:
            return "UNVERIFIABLE"
        # 计算型：gt==0 → 绝对 0.01；否则相对 0.5%
        passed = (dv is not None) and (dv < ABS_TOL if gt == 0 else dv / abs(gt) < REL_TOL)
        return "PASS" if passed else "FAIL"

    if claim_type == "comparative":
        # 方向存在性判定：equal_to 可复判（delta < 0.01）；greater/less 需符号 → 离线不可判
        direction = claim.get("stated_value")
        if direction == "equal_to":
            if dv is None:
                return "UNVERIFIABLE"
            return "PASS" if dv < ABS_TOL else "FAIL"
        return "UNVERIFIABLE"

    # temporal / entity / regulatory 等：verify_claims 走 else 分支 → UNVERIFIABLE
    return "UNVERIFIABLE"


def _rejudge_semantic(claim: dict) -> Status | None:
    """语义层离线复判（harden-citation-semantic-coverage 镜像 citation.py）：

    term 检查纯字符串（metric_name 规范键 vs field_ref 指标段）；
    period 检查仅显式期次段可比（索引锚定离线无从解析 → None 跳过，与
    管线「计缺口不 FAIL」对齐——baseline 的索引锚定样本期次维度不计检出）。
    返回 "FAIL" 或 None（通过/不适用）。
    """
    from finance_agent.metric_vocab import (
        canonical_metric,
        field_ref_metric_segments,
        field_ref_period_segment,
        period_matches,
    )

    field_ref = str(claim.get("field_ref") or "")
    metric_name = (claim.get("metric_name") or "").strip()
    if metric_name:
        canonical = canonical_metric(metric_name)
        # 词表外（无规范键）→ 跳过（镜像管线 D5 扩展：计缺口不 FAIL）
        if canonical is not None:
            seg_keys = {(canonical_metric(s) or s) for s in field_ref_metric_segments(field_ref)}
            if canonical not in seg_keys:
                return "FAIL"
    period = (claim.get("period") or "").strip()
    if period:
        actual = field_ref_period_segment(field_ref)
        if actual is not None and not period_matches(period, actual):
            return "FAIL"
    return None


def _rejudge_event(claim: dict, ground_truth: object | None) -> Status:
    """事件型：gt 存在（事件被解析到）→ 比日期；gt 缺失 → 离线不可判。"""
    if ground_truth is None:
        return "UNVERIFIABLE"
    stated = claim.get("stated_value")
    if stated:
        return "PASS" if str(ground_truth) == str(stated) else "FAIL"
    return "PASS"  # 事件存在且无日期断言（镜像 _verify_event 的「存在即 PASS」）


def _coerce_numeric(value: object | None) -> float | None:
    """数值化 ground_truth / delta；非数值（None/str 非数/容器）返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def is_hedged(claim: dict) -> bool:
    """hedged 子集判定：stated_value / interpretation 含模糊措辞。"""
    hay = f"{claim.get('stated_value', '')} {claim.get('interpretation', '')}"
    return any(w in hay for w in HEDGE_WORDS)


# ── 契约疾病标记（预修复 trace 的回归考题识别）───────────────────────────
# 修 A/B 前的 LLM 书写习惯：技术面用裁剪窗口正索引；根键用中文段落标题。
# 这些样本的 gt 在旧解析层下不可信/不可得，离线复判无意义 —— 标记后由
# 调用方计入 regression 子集单独披露（人工标签仍给出，供后续 post-fix trace 复验）。
_CN_ROOT_MAP = {
    "盈利能力": "profitability_metrics",
    "偿债能力": "solvency_metrics",
    "运营效率": "efficiency_metrics",
    "现金流": "cashflow_metrics",
    "杜邦分析": "dupont_tree",
    "增长率": "growth_rates",
    "利润表": "income_statement",
    "资产负债表": "balance_sheet",
    "现金流量表": "cash_flow_statement",
    "季度趋势": "quarterly_trend",
    "健康度评分": "health_score",
    "预计算指标": "financial_indicators",
}


def contract_disease(claim: dict, *, pre_fix: bool) -> str | None:
    """识别旧契约疾病特征（仅 pre_fix trace 有意义）；无疾病返回 None。

    Returns:
        "index"  — technical_indicators 路径尾段为非负整数（旧窗口正索引语义）
        "wordlist" — 根键为中文段落标题或旧 events 根键（词表分裂）
        None    — 无疾病特征
    """
    if not pre_fix:
        return None
    field_ref = str(claim.get("field_ref") or "")
    parts = field_ref.split(".")
    root = parts[0].split("[")[0]
    if root == "technical_indicators" and len(parts) >= 4 and parts[-1].isdigit():
        return "index"
    if root in _CN_ROOT_MAP or root == "events":
        return "wordlist"
    return None
