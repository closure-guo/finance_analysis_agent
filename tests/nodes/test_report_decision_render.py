"""TDD tests for update-decision-integrity-gates Task 2/3 — 交易决策节渲染。

Task 2：非法仓位档位字面量归一渲染（report-decision-rendering「参数缺失时诚实标注」
MODIFIED：档位词表 light/moderate/heavy 大小写不敏感，非法字面量渲染前归一为缺失
「未提供」，归一 MUST NOT 回写决策对象）。
Task 3：buy/sell 终稿再评估触发条件渲染（缺失「未申报」）；update-decision-price-gate：
报警仅进 trace，渲染链不接收 anomalies。
"""

import inspect

import pytest

from finance_agent.models import TradeDecision
from finance_agent.nodes.report import (
    _fmt_reeval_triggers,
    _format_trade_decision,
    generate_report,
)


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


class TestBuySellReevalTriggersRender:
    """Task 3：buy/sell 也渲染「再评估触发条件」行（report-decision-rendering
    「交易决策节渲染操作参数」MODIFIED：非空逐条编号；空/缺「未申报」不省略整行）。"""

    @staticmethod
    def _buy_state(decision: TradeDecision | dict) -> dict:
        return {"stock_code": "601818", "final_trade_decision": decision}

    def test_buy_full_triggers_numbered_and_ordered(self):
        state = self._buy_state(
            {
                "action": "buy",
                "confidence": 0.55,
                "position_size": "light",
                "entry_price": 6.12,
                "stop_loss": 5.8,
                "target_price": 6.8,
                "reasoning": "r",
                "reeval_triggers": ["跌破 5.8 元止损离场", "放量站上 20 日线加仓"],
            }
        )
        md = generate_report(state)["final_report"]
        assert "- **再评估触发条件**: ① 跌破 5.8 元止损离场；② 放量站上 20 日线加仓" in md
        # spec 顺序：…入场价、止损价、目标价、再评估触发条件、理由
        order = [
            md.index(k)
            for k in ("**入场价**", "**止损价**", "**目标价**", "**再评估触发条件**", "**理由**")
        ]
        assert order == sorted(order)

    def test_sell_empty_triggers_marked_unreported(self):
        """601818 形态：sell 清洗后触发条件为空（含「已打回仍未申报」终检形态）→
        「未申报」行保留，不省略整行、不编造条目。"""
        state = self._buy_state(
            {
                "action": "sell",
                "confidence": 0.52,
                "position_size": "light",
                "entry_price": 3.42,
                "stop_loss": 0,
                "target_price": 0,
                "reasoning": "维持卖出方向",
                "reeval_triggers": [],
            }
        )
        md = generate_report(state)["final_report"]
        assert "- **再评估触发条件**: 未申报" in md
        assert md.count("- **再评估触发条件**:") == 1

    def test_buy_missing_triggers_key_renders_unreported(self):
        """buy 决策无 reeval_triggers 键 → 「未申报」（MUST NOT 整行省略）。"""
        state = self._buy_state(
            {
                "action": "buy",
                "confidence": 0.5,
                "position_size": "light",
                "entry_price": 10.0,
                "stop_loss": 9.0,
                "target_price": 12.0,
                "reasoning": "r",
            }
        )
        md = generate_report(state)["final_report"]
        assert "- **再评估触发条件**: 未申报" in md

    def test_watch_legacy_object_without_fields(self):
        """watch 旧决策对象（无 inaction_reason/reeval_triggers 字段）→ 「未申报」，
        渲染不因字段缺失抛异常。"""
        state = {
            "stock_code": "600519",
            "final_trade_decision": {"action": "watch", "confidence": 0.5, "reasoning": "r"},
        }
        md = generate_report(state)["final_report"]
        assert "- **不行动原因**: 未申报" in md
        assert "- **再评估触发条件**: 未申报" in md


class TestPriceAlarmNeverRendered:
    """update-decision-price-gate：报警信息属于内部 trace——报告 MUST NOT 渲染
    「价位待核实」类标注；渲染链签名不再接收 anomalies（阻断语义下报告只可能
    由无残留 anomaly 的终稿产出）。"""

    ANOMALY = {
        "kind": "deviation",
        "source_text": "价格回落至 1500 以下",
        "indicator": "近期低点",
        "verified_value": 1450.0,
        "deviation_pct": 3.45,
        "message": "文本价位 1500 与近期低点已验证值 1450 偏差 3.45%，价位待核实",
    }

    def test_rendering_chain_no_longer_accepts_anomalies(self):
        assert "anomalies" not in inspect.signature(_format_trade_decision).parameters
        assert "anomalies" not in inspect.signature(_fmt_reeval_triggers).parameters
        # anomalies 实参必须被拒绝（签名收窄后 TypeError）
        with pytest.raises(TypeError):
            _format_trade_decision(
                TradeDecision.model_validate(
                    {
                        "action": "watch",
                        "confidence": 0.5,
                        "reasoning": "r",
                        "inaction_reason": "等待回落确认",
                        "reeval_triggers": ["价格回落至 1500 以下", "跌破 1400 元离场"],
                    }
                ),
                [self.ANOMALY],  # type: ignore[call-arg]
            )

    def test_trigger_entry_rendered_without_annotation(self):
        decision = TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "r",
                "inaction_reason": "等待回落确认",
                "reeval_triggers": ["价格回落至 1500 以下", "跌破 1400 元离场"],
            }
        )
        md = _format_trade_decision(decision)
        assert "① 价格回落至 1500 以下" in md
        assert "价位待核实" not in md
        assert "② 跌破 1400 元离场" in md

    def test_sell_reasoning_rendered_without_annotation(self):
        decision = TradeDecision.model_validate(
            {
                "action": "sell",
                "confidence": 0.55,
                "reasoning": "股价跌破近期低点 26.28 支撑，趋势走弱",
                "entry_price": 26.0,
                "stop_loss": 27.5,
                "target_price": 24.0,
                "reeval_triggers": ["反弹至 27.5 元减仓"],
            }
        )
        md = _format_trade_decision(decision)
        assert "- **理由**: 股价跌破近期低点 26.28 支撑，趋势走弱" in md
        assert "价位待核实" not in md
