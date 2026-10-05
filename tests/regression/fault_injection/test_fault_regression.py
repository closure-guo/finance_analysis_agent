# tests/regression/fault_injection/test_fault_regression.py
"""故障注入回归集（add-fault-injection-regression-set，issue #232）。

七轮人工评审（拓荆 688072，2026-10-04 至 10-05）暴露的真实故障样本固化：
每次改 prompt、换模型、升级校验器后先跑本回归集，守卫被削弱即红。
全程确定性零 token。样本来源与修复版本见同目录 README.md。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from finance_agent.citation import Claim, verify_claims
from finance_agent.llm.output_guard import validate_deliverable_text
from finance_agent.nodes import report as report_module
from finance_agent.nodes.report import _format_trade_decision

_SAMPLES = Path(__file__).parent / "samples"


def _sample(name: str) -> str:
    return (_SAMPLES / name).read_text(encoding="utf-8")


# ── F1 推理泄露（v5：换模型后格式契约崩，修复=llm-output-contract）──


@pytest.mark.fault_regression
class TestF1ReasoningLeak:
    def test_incident_036_sample_rejected(self):
        v = validate_deliverable_text(_sample("v5_leak_focus_036.txt"))
        assert v.ok is False
        assert "leak:the_user_wants" in v.hits
        assert "leak:draft_marker" in v.hits
        assert "truncated:tail" in v.hits

    def test_english_monologue_rejected(self):
        v = validate_deliverable_text(_sample("v5_leak_english_monologue.txt"))
        assert v.ok is False
        assert any(h.startswith("leak:") for h in v.hits)

    def test_truncated_tail_rejected(self):
        v = validate_deliverable_text(_sample("v5_leak_truncated.txt"))
        assert v.ok is False
        assert "truncated:tail" in v.hits

    def test_clean_reference_not_flagged(self):
        """防误伤哨兵：干净中文成稿必须直通。"""
        v = validate_deliverable_text(_sample("v5_clean_reference.txt"))
        assert v.ok is True, f"干净样本被误伤: hits={v.hits}"


# ── F2 报警外露（v2：价位校验报警文案泄入成稿，修复=update-decision-price-gate）──


@pytest.mark.fault_regression
class TestF2AlarmExposure:
    def test_anomaly_dict_injection_not_rendered(self):
        """decision dict 被注入 anomalies 键（模拟渲染链重新接收）也不得外泄。"""
        decision = {
            "action": "watch",
            "confidence": 0.55,
            "reasoning": "多空证据大体均衡，等待三季报验证毛利率修复持续性",
            "re_eval_triggers": ["股价有效突破 MA60 且量能配合"],
            "decision_price_anomalies": [
                "价位校验报警: 决策价 95 元偏离快照价超 5%，建议复核（95元样本）"
            ],
        }
        rendered = _format_trade_decision(decision)
        assert "价位校验" not in rendered
        assert "95" not in rendered

    def test_render_chain_does_not_read_anomalies(self):
        """结构护栏：渲染链源码不得读取 decision_price_anomalies（v2 修复的结构约束）。"""
        source = inspect.getsource(report_module)
        assert "decision_price_anomalies" not in source


# ── F3 期次错位/同值撞车（v1 + 41.69% 实例，修复=add-period-key-citation-validation）──


def _collision_state() -> dict:
    """41.69 年报/单季撞车 state（拓荆 688072 终裁实证：两期次值真实相等）。"""
    return {
        "profitability_metrics": {"毛利率": {"2023": 47.11, "2024": 41.69, "2025": 34.95}},
        "quarterly_trend": {
            "quarters": ["2026Q2", "2026Q1", "2025Q4", "2025Q3"],
            "gross_margin": [40.58, 41.69, 38.02, 34.42],
        },
    }


@pytest.mark.fault_regression
class TestF3PeriodCollision:
    def test_marker_mismatch_rejected(self):
        """v4 故障形态：正文标 2026Q1、登记 2024 年报键。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=41.69,
            interpretation="2026Q1单季毛利率41.69%",
            metric_name="毛利率",
            period="2024",
            direction="flat",
        )
        (result,) = verify_claims([claim], _collision_state())
        assert result.status == "FAIL"
        assert result.bucket == "semantic_period_mismatch"

    def test_ambiguous_bare_value_rejected(self):
        """撞车值裸引（无期次标注）→ 消歧义务未履行。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=41.69,
            interpretation="毛利率41.69%，处于低位",
            metric_name="毛利率",
            period="2024",
            direction="flat",
        )
        (result,) = verify_claims([claim], _collision_state())
        assert result.status == "FAIL"
        assert result.bucket == "ambiguous_value_undisambiguated"

    def test_disambiguated_value_accepted(self):
        """v7 修复形态：显式认领期次 → 放行。"""
        claim = Claim(
            claim_type="numerical",
            source_type="data",
            field_ref="profitability_metrics.毛利率.2024",
            stated_value=41.69,
            interpretation="2024年报毛利率41.69%，同比下滑",
            metric_name="毛利率",
            period="2024",
            direction="flat",
        )
        (result,) = verify_claims([claim], _collision_state())
        assert result.status == "PASS"
