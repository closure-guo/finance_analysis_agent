"""同值跨期次歧义消解校验（add-period-key-citation-validation）。

基准实例：拓荆 688072 第七轮人工评审——2024 年报毛利率与 2026Q1 单季毛利率
均为 41.69%，v4 正文标注 2026Q1、v7 标注 2024 年报，期次归属随 LLM 采样漂移，
现有值存在性/期次声明校验全部通过（issue #231）。
"""

from __future__ import annotations

from finance_agent.citation import Claim, verify_claims


def _collision_state() -> dict:
    """41.69 年报/单季撞车 state（41.69 真实存在于两个期次锚点）。"""
    return {
        "profitability_metrics": {
            "毛利率": {
                "2023": 47.11,
                "2024": 41.69,
                "2025": 34.95,
            }
        },
        "quarterly_trend": {
            "quarters": ["2026Q2", "2026Q1", "2025Q4", "2025Q3"],
            "gross_margin": [40.58, 41.69, 38.02, 34.42],
        },
    }


def _claim(interpretation: str, field_ref: str = "profitability_metrics.毛利率.2024") -> Claim:
    return Claim(
        claim_type="numerical",
        source_type="data",
        field_ref=field_ref,
        stated_value=41.69,
        interpretation=interpretation,
        metric_name="毛利率",
        period="2024",
        direction="flat",
    )


def test_marker_mismatch_fails() -> None:
    """interpretation 标注 2026Q1 而 field_ref 溯源 2024 年报 → 标记错配 FAIL。"""
    (result,) = verify_claims([_claim("2026Q1单季毛利率41.69%")], _collision_state())
    assert result.status == "FAIL"
    assert result.bucket == "semantic_period_mismatch"


def test_ambiguous_without_marker_fails() -> None:
    """撞车值无期次标记 → 消歧义务未履行 FAIL。"""
    (result,) = verify_claims([_claim("毛利率41.69%，处于低位")], _collision_state())
    assert result.status == "FAIL"
    assert result.bucket == "ambiguous_value_undisambiguated"


def test_explicit_marker_passes() -> None:
    """显式认领 field_ref 期次（2024 年报）→ 放行。"""
    (result,) = verify_claims([_claim("2024年报毛利率41.69%，同比大幅下滑")], _collision_state())
    assert result.status == "PASS"


def test_extra_markers_allowed() -> None:
    """提及别的期次不拦截——只要求 field_ref 期次被认领。"""
    (result,) = verify_claims(
        [_claim("2024年报毛利率41.69%，低于2026Q1修复水平")], _collision_state()
    )
    assert result.status == "PASS"


def test_unique_anchor_without_marker_passes() -> None:
    """唯一锚点值无标记 → 不受消歧义务约束（不误伤）。"""
    claim = _claim("毛利率34.95%，处于低位", field_ref="profitability_metrics.毛利率.2025")
    claim.stated_value = 34.95
    claim.period = "2025"
    (result,) = verify_claims([claim], _collision_state())
    assert result.status == "PASS"


def test_marker_mismatch_independent_of_collision() -> None:
    """标记错配检查独立于值歧义：唯一锚点值 + 错配期次标记 → 仍 FAIL。"""
    claim = _claim("2026Q1单季毛利率34.95%", field_ref="profitability_metrics.毛利率.2025")
    claim.stated_value = 34.95
    claim.period = "2025"
    (result,) = verify_claims([claim], _collision_state())
    assert result.status == "FAIL"
    assert result.bucket == "semantic_period_mismatch"


def test_comparative_exempt() -> None:
    """比较型 claim 豁免消歧检查：interpretation 必含基期期次，由双端申报结构承担。"""
    from finance_agent.citation import _check_period_disambiguation

    claim = Claim(
        claim_type="comparative",
        source_type="data",
        field_ref="profitability_metrics.毛利率.2025",
        field_ref_b="profitability_metrics.毛利率.2024",
        stated_value=34.95,
        stated_value_b=41.69,
        interpretation="2025年报毛利率34.95%，较2024年的41.69%继续下滑",
        metric_name="毛利率",
        period="2025",
    )
    assert _check_period_disambiguation(claim, _collision_state()) is None
    # 全链弱断言：比较型不经消歧检查变 FAIL（值级可能因差值申报契约 UNVERIFIABLE，
    # 那是既有行为，不属于本 delta 语义）
    (result,) = verify_claims([claim], _collision_state())
    assert result.bucket not in ("ambiguous_value_undisambiguated", "semantic_period_mismatch")


def test_quarterly_field_ref_claim_passes_with_marker() -> None:
    """field_ref 指向单季序列锚点时，认领对应季度即放行。"""
    claim = _claim("2026Q1单季毛利率41.69%", field_ref="quarterly_trend.gross_margin.1")
    claim.period = "2026Q1"
    (result,) = verify_claims([claim], _collision_state())
    assert result.status == "PASS"


def test_unparseable_marker_treated_as_no_marker() -> None:
    """「单季」等无年份词归一失败 → 视为无标记：撞车值拦、唯一锚点放。"""
    (result,) = verify_claims([_claim("单季毛利率41.69%")], _collision_state())
    assert result.status == "FAIL"
    assert result.bucket == "ambiguous_value_undisambiguated"


def test_ambiguous_bucket_not_repairable() -> None:
    """歧义桶不进确定性单点修复白名单（repair 分流只捡 value_mismatch）。

    锁定 citation_node.py 的分流常量：歧义桶 FAIL 走定向重试由分析师补标注，
    不做 LLM 改写——正文期次标注是分析语义，程序侧无可确定性修复的目标值。
    """
    (result,) = verify_claims([_claim("毛利率41.69%，处于低位")], _collision_state())
    assert result.status == "FAIL"
    assert result.bucket == "ambiguous_value_undisambiguated"
    assert result.bucket != "value_mismatch"


def test_collision_state_absent_no_crash() -> None:
    """state 无序列段时消歧检查按缺口降级，不误伤不炸管线。"""
    (result,) = verify_claims([_claim("毛利率41.69%")], {"kline": None})
    assert result.status in ("PASS", "FAIL", "UNVERIFIABLE")
