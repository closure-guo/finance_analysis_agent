"""TDD tests for nodes/trader.py — Layer III Trader Agent。"""

import json
from unittest.mock import patch

from finance_agent.nodes.trader import _build_trader_context, trader


def _mock_trader_response() -> str:
    return json.dumps(
        {
            "action": "buy",
            "confidence": 0.75,
            "reasoning": "ROE 持续高于 15%，负债率健康，估值合理",
            "position_size": "moderate",
            "entry_price": 1500.0,
            "stop_loss": 1400.0,
            "target_price": 1800.0,
        },
        ensure_ascii=False,
    )


class TestTrader:
    """Layer III Trader Agent。"""

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_produces_trade_decision(self, mock_llm):
        mock_llm.return_value = _mock_trader_response()
        state = {
            "analyst_reports": {},
            "research_manager_conclusion": "基本面强劲，建议关注",
        }
        result = trader(state)
        assert "trader_plan" in result
        decision = result["trader_plan"]
        assert decision.action == "buy"
        assert decision.confidence == 0.75
        assert decision.target_price == 1800.0


class TestTraderReturnFeedback:
    """calibrate-fm-approval：FM return 重跑时 Trader context 必须携带退回理由。

    取证（2026-09-04，Langfuse 153 条 fund_manager trace）：FM 行为健康
    （approve 53%），但 return→trader 重跑未注入 fund_manager_decision_reasoning，
    Trader 产出同方案 → FM 依风控职责再拒 → 用户只见 reject。
    本测试守护注入语义：return 场景必须带反馈，非 return 场景不得注入。
    """

    def test_context_includes_fm_return_reasoning(self):
        state = {
            "analyst_reports": {},
            "fund_manager_decision": "return",
            "fund_manager_decision_reasoning": "请补充仓位控制与止损安排后再提交",
        }
        context = _build_trader_context(state)
        assert "基金经理退回意见" in context
        assert "请补充仓位控制与止损安排后再提交" in context

    def test_context_without_fm_feedback_stays_clean(self):
        # approve/reject 路径（非 return 重跑）不得注入退回意见，避免误导 Trader
        state = {
            "analyst_reports": {},
            "fund_manager_decision": "approve",
        }
        context = _build_trader_context(state)
        assert "基金经理退回意见" not in context

    def test_context_with_empty_reasoning_not_injected(self):
        # 空理由视为无反馈：不注入空段落，保留既有行为
        state = {
            "analyst_reports": {},
            "fund_manager_decision_reasoning": "",
        }
        context = _build_trader_context(state)
        assert "基金经理退回意见" not in context
