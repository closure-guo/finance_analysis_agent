"""TDD tests for update-decision-integrity-gates Task 3 — buy/sell 终稿 reeval_triggers 必填化。

spec agent-node-contracts「非执行动作结构化理由契约」MODIFIED：
- 终稿执行动作缺再评估触发条件打回一次后放行（与 final_price_check 同款一次重试语义，
  feedback 引用风险辩论共识线索）；重试后仍缺失 → 放行 + final_reeval_check note
  「已打回仍未申报」；
- 终稿执行动作触发条件齐备直通（pass，无打回无标注）；
- 噪声形态清洗不炸管线（TradeDecision 模型层既有清洗，本文件锁定行为）。

mock 模式与 tests/nodes/test_risk.py 既有一致：patch
finance_agent.nodes._llm_utils.call_llm_streaming。
"""

import json
from unittest.mock import patch

from finance_agent.models import TradeDecision
from finance_agent.nodes.risk import risk_judge


def _resp(action: str = "buy", **fields: object) -> str:
    """默认 buy/sell 完整价位（隔离价位回路，只测再评估触发条件回路）。"""
    payload: dict = {
        "action": action,
        "confidence": 0.6,
        "reasoning": "风险可控",
        "position_size": "light",
        "entry_price": 26.35,
        "stop_loss": 25.3,
        "target_price": 28.0,
    }
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False)


class TestFinalReevalCheck:
    """终稿执行动作再评估触发条件必填化（risk_judge 三路检查的最后一路）。"""

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_buy_empty_triggers_retries_once_then_fills(self, mock_llm):
        """buy 缺触发条件 → 打回一次（第二次补齐），feedback 引用风险辩论共识线索。"""
        mock_llm.side_effect = [
            _resp(),  # 第一次：buy 价位齐备但 reeval_triggers 缺失
            _resp(reeval_triggers=["跌破 25.3 元止损离场", "放量站上 20 日线确认趋势"]),
        ]
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        # 打回反馈拼进重试（第二次）调用的 context，并引用辩论共识线索
        retry_context = mock_llm.call_args_list[1].args[0]
        assert "再评估触发条件打回" in retry_context
        assert "保守/中性方已提出的触发条件" in retry_context
        assert result["final_reeval_check"] == {"result": "pass", "note": "打回后已申报"}
        assert result["final_trade_decision"].reeval_triggers == [
            "跌破 25.3 元止损离场",
            "放量站上 20 日线确认趋势",
        ]

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_601818_sell_retry_exhausted_annotated_and_released(self, mock_llm):
        """601818 形态：sell 终稿无触发条件 → 打回一次 → 仍空 → 放行 + 如实标注。"""
        mock_llm.return_value = _resp(action="sell", reeval_triggers=[])
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        assert result["final_trade_decision"].action == "sell"  # 放行，不虚构条目
        assert result["final_reeval_check"]["result"] == "pass"
        assert result["final_reeval_check"]["note"] == "已打回仍未申报再评估触发条件"
        assert result["final_trade_decision"].reeval_triggers == []

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_buy_with_triggers_passes_without_retry(self, mock_llm):
        """触发条件齐备（≥1 条）→ 直通：无打回、无标注。"""
        mock_llm.return_value = _resp(reeval_triggers=["跌破止损位离场"])
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 1
        assert result["final_reeval_check"] == {"result": "pass", "note": ""}

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_watch_not_applicable(self, mock_llm):
        """watch/hold 不适用本检查（理由完整性由 final_inaction_check 承担），无额外打回。"""
        mock_llm.return_value = _resp(
            action="watch",
            entry_price=None,
            stop_loss=None,
            target_price=None,
            inaction_reason="等待右侧信号",
            reeval_triggers=["放量站上 20 日线"],
        )
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 1
        assert result["final_reeval_check"] == {"result": "pass", "note": ""}

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_reeval_retry_to_buy_missing_prices_annotates_price_note(self, mock_llm):
        """再评估重试使终稿换代 → 复核价位结论：换代后价位缺失须如实改注（不再次打回）。"""
        mock_llm.side_effect = [
            _resp(),  # buy 价位齐备、触发条件缺失
            _resp(
                entry_price=None,
                stop_loss=None,
                target_price=None,
                reeval_triggers=["跌破止损位离场"],
            ),  # 重试换代后价位缺失
        ]
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        note = result["final_price_check"]["note"]
        assert "再评估重试后终稿价位缺失" in note
        assert "entry_price" in note
        assert result["final_reeval_check"]["note"] == "打回后已申报"

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_reeval_retry_to_watch_missing_rationale_annotates_inaction_note(self, mock_llm):
        """再评估重试换代为 watch 且理由缺失 → 复核理由结论：如实改注（不再次打回）。"""
        mock_llm.side_effect = [
            _resp(),  # buy 价位齐备、触发条件缺失
            _resp(action="watch", entry_price=None, stop_loss=None, target_price=None),
        ]
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        assert result["final_trade_decision"].action == "watch"
        note = result["final_inaction_check"]["note"]
        assert "再评估重试后终稿改为非执行动作且理由缺失" in note
        assert "inaction_reason" in note and "reeval_triggers" in note

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_reeval_retry_to_watch_complete_rationale_keeps_checks_clean(self, mock_llm):
        """再评估重试换代为 watch 且理由齐备：前序结论维持 pass 空注（不产生假标注）。"""
        mock_llm.side_effect = [
            _resp(),
            _resp(
                action="watch",
                entry_price=None,
                stop_loss=None,
                target_price=None,
                inaction_reason="估值分位偏高",
                reeval_triggers=["放量站上 20 日线"],
            ),
        ]
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert mock_llm.call_count == 2
        assert result["final_price_check"] == {"result": "pass", "note": ""}
        assert result["final_inaction_check"] == {"result": "pass", "note": ""}
        assert result["final_reeval_check"]["note"] == "打回后已申报"


class TestReevalTriggersModelCleaning:
    """噪声形态清洗不炸管线（TradeDecision 模型层既有清洗——锁定行为防回退）。"""

    @staticmethod
    def _decision(**fields: object) -> TradeDecision:
        return TradeDecision.model_validate(
            {"action": "buy", "confidence": 0.6, "reasoning": "r", **fields}
        )

    def test_none_normalized_to_empty_list(self):
        assert self._decision(reeval_triggers=None).reeval_triggers == []

    def test_single_string_normalized_to_single_item_list(self):
        assert self._decision(reeval_triggers="跌破 25 元").reeval_triggers == ["跌破 25 元"]

    def test_pure_whitespace_string_normalized_to_empty(self):
        assert self._decision(reeval_triggers="   ").reeval_triggers == []

    def test_mixed_list_drops_non_string_and_blank_entries(self):
        decision = self._decision(reeval_triggers=["有效条件", 123, "  ", None, "第二条"])
        assert decision.reeval_triggers == ["有效条件", "第二条"]

    def test_non_list_noise_normalized_to_empty(self):
        assert self._decision(reeval_triggers={"reason": "x"}).reeval_triggers == []

    def test_default_field_is_empty_list(self):
        assert self._decision().reeval_triggers == []

    def test_noise_forms_do_not_raise_validation_error(self):
        """清洗 MUST NOT 抛 ValidationError 中断管线（逐形态验证）。"""
        for noise in (None, "单字符串", ["a", 1, None, "b"], {"x": 1}, 42):
            TradeDecision.model_validate(
                {"action": "sell", "confidence": 0.5, "reasoning": "r", "reeval_triggers": noise}
            )
