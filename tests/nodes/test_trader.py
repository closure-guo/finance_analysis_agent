"""TDD tests for nodes/trader.py — Layer III Trader Agent。"""

import json
from unittest.mock import patch

from finance_agent.nodes.trader import trader


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

    @patch("finance_agent.nodes.trader.call_llm")
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
