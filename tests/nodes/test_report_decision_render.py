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


class TestPriceAnomalyAnnotation:
    """Task 3：决策文本与 decision_price_anomalies source_text 同源 → 条目旁标注
    「（价位待核实：<message>）」（字符串包含关系；source_text 的省略号是
    _excerpt 渲染产物，剥除后匹配）。"""

    ANOMALY = {
        "kind": "deviation",
        "source_text": "价格回落至 1500 以下",
        "indicator": "近期低点",
        "verified_value": 1450.0,
        "deviation_pct": 3.45,
        "message": "文本价位 1500 与近期低点已验证值 1450 偏差 3.45%，价位待核实",
    }

    def test_matching_trigger_entry_annotated(self):
        decision = TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "r",
                "inaction_reason": "等待回落确认",
                "reeval_triggers": ["价格回落至 1500 以下", "跌破 1400 元离场"],
            }
        )
        md = _format_trade_decision(decision, [self.ANOMALY])
        assert (
            "① 价格回落至 1500 以下（价位待核实：文本价位 1500 与近期低点已验证值 "
            "1450 偏差 3.45%，价位待核实）"
        ) in md
        # 未命中条目不标注
        assert "② 跌破 1400 元离场（" not in md

    def test_inaction_reason_excerpt_with_ellipsis_annotated(self):
        """excerpt 形态 source_text（带 … 渲染产物）剥除后仍可同源匹配。"""
        anomaly = {
            "kind": "empty_trigger",
            "source_text": "…触发条件：站上 26.5 才算…",
            "indicator": "最新收盘价",
            "verified_value": 27.0,
            "deviation_pct": None,
            "message": "上破触发价位 26.5 不高于最新收盘价 27.0，不构成有效再评估门槛",
        }
        decision = TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "r",
                "inaction_reason": "当前触发条件：站上 26.5 才算右侧确认",
                "reeval_triggers": [],
            }
        )
        md = _format_trade_decision(decision, [anomaly])
        assert "（价位待核实：上破触发价位 26.5 不高于最新收盘价 27.0，不构成有效再评估门槛）" in md

    def test_reasoning_annotated_for_sell(self):
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
        anomaly = {
            "kind": "deviation",
            "source_text": "近期低点 26.28 支撑",
            "indicator": "近期低点",
            "verified_value": 25.9,
            "deviation_pct": 1.47,
            "message": "文本价位 26.28 与近期低点已验证值 25.9 偏差 1.47%，价位待核实",
        }
        md = _format_trade_decision(decision, [anomaly])
        assert "- **理由**: 股价跌破近期低点 26.28 支撑，趋势走弱（价位待核实：" in md

    def test_no_anomalies_no_extra_rendering(self):
        """方案完整（无 anomalies）→ 维持现状形态，不出现空标注。"""
        decision = TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "r",
                "inaction_reason": "等待",
                "reeval_triggers": ["跌破 25 元"],
            }
        )
        md = _format_trade_decision(decision, [])
        assert "价位待核实" not in md
        assert "- **再评估触发条件**: ① 跌破 25 元" in md

    def test_state_anomalies_flow_into_report(self):
        """state["decision_price_anomalies"]（Task 1 risk_judge 产出）流入渲染标注。"""
        state = {
            "stock_code": "600519",
            "final_trade_decision": {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "r",
                "inaction_reason": "等待回落确认",
                "reeval_triggers": ["价格回落至 1500 以下"],
            },
            "decision_price_anomalies": [self.ANOMALY],
        }
        md = generate_report(state)["final_report"]
        assert "价位待核实：文本价位 1500" in md

    def test_anomaly_shape_noise_tolerated(self):
        """anomalies 形态噪声（非 dict / 缺键）不炸渲染。"""
        decision = TradeDecision.model_validate(
            {"action": "watch", "confidence": 0.5, "reasoning": "r", "reeval_triggers": ["x 条件"]}
        )
        md = _format_trade_decision(decision, ["not-a-dict", {"kind": "deviation"}, None])  # type: ignore[list-item]
        assert "- **再评估触发条件**: ① x 条件" in md
        assert "价位待核实" not in md
