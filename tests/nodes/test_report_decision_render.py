"""TDD tests for update-decision-integrity-gates Task 2/3 — 交易决策节渲染。

Task 2：非法仓位档位字面量归一渲染（report-decision-rendering「参数缺失时诚实标注」
MODIFIED：档位词表 light/moderate/heavy 大小写不敏感，非法字面量渲染前归一为缺失
「未提供」，归一 MUST NOT 回写决策对象）。
Task 3：buy/sell 终稿再评估触发条件渲染（缺失「未申报」）+ decision_price_anomalies
同源「价位待核实」标注。
"""

import pytest

from finance_agent.models import TradeDecision
from finance_agent.nodes.report import _format_trade_decision, generate_report


@pytest.fixture(autouse=True)
def _stub_focus_summary(monkeypatch):
    """研究聚焦摘要打桩（不烧 LLM，渲染测试只关心交易决策节）。"""
    from finance_agent.nodes import report as report_mod

    monkeypatch.setattr(report_mod, "complete_text", lambda *a, **k: ("聚焦摘要（测试数据）", {}))


class TestPositionSizeVocabNormalization:
    """非法仓位档位字面量归一渲染（600515 实证：watch 决策 position_size="none"
    原样透传到报告）。"""

    @staticmethod
    def _state(decision: TradeDecision | dict) -> dict:
        return {"stock_code": "600515", "final_trade_decision": decision}

    def test_illegal_literal_none_renders_weitigong(self):
        """600515 形态：position_size="none" 不在词表 → 渲染「未提供」，不透传字面量。"""
        decision = {
            "action": "watch",
            "confidence": 0.5,
            "position_size": "none",
            "reasoning": "多因素均衡",
            "inaction_reason": "等待右侧信号",
            "reeval_triggers": ["放量站上 20 日线"],
        }
        md = generate_report(self._state(decision))["final_report"]
        assert "- **仓位**: 未提供" in md
        assert "- **仓位**: none" not in md

    @pytest.mark.parametrize("literal", ["null", "", "  ", "full", "30%", None])
    def test_other_illegal_literals_renders_weitigong(self, literal):
        """词表外其余非法形态（"null"/空串/纯空白/自由文本/None）一律「未提供」。"""
        decision = {
            "action": "watch",
            "confidence": 0.5,
            "position_size": literal,
            "reasoning": "r",
            "inaction_reason": "等待",
            "reeval_triggers": ["放量站上 20 日线"],
        }
        md = generate_report(self._state(decision))["final_report"]
        assert "- **仓位**: 未提供" in md

    @pytest.mark.parametrize("level", ["light", "moderate", "heavy", "Light", "MODERATE", "Heavy"])
    def test_valid_levels_render_original_value(self, level):
        """合法档位（含大小写变体）按原值渲染，MUST NOT 归一为「未提供」。"""
        decision = {
            "action": "buy",
            "confidence": 0.5,
            "position_size": level,
            "entry_price": 10.0,
            "stop_loss": 9.0,
            "target_price": 12.0,
            "reasoning": "r",
            "reeval_triggers": ["跌破 9 元止损离场"],
        }
        md = generate_report(self._state(decision))["final_report"]
        assert f"- **仓位**: {level}" in md

    def test_normalization_does_not_mutate_decision_dict(self):
        """归一只作用于渲染：dict 决策对象原值保留（落库与 trace 可观测）。"""
        decision = {
            "action": "watch",
            "confidence": 0.5,
            "position_size": "none",
            "reasoning": "r",
            "inaction_reason": "等待",
            "reeval_triggers": [],
        }
        generate_report(self._state(decision))
        assert decision["position_size"] == "none"

    def test_normalization_does_not_mutate_decision_object(self):
        """归一只作用于渲染：pydantic 决策对象属性原值保留。"""
        decision = TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.5,
                "position_size": "none",
                "reasoning": "r",
                "inaction_reason": "等待",
                "reeval_triggers": [],
            }
        )
        generate_report(self._state(decision))
        assert decision.position_size == "none"

    def test_legacy_dict_without_position_key(self):
        """历史 dict 无 position_size 键 → 「未提供」，不抛异常。"""
        decision = {"action": "watch", "confidence": 0.5, "reasoning": "r"}
        md = _format_trade_decision(decision)
        assert "- **仓位**: 未提供" in md
