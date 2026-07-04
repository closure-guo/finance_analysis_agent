"""TDD tests for nodes/fund_manager.py — Layer V Fund Manager Agent。"""

import json
from unittest.mock import patch

from finance_agent.nodes.fund_manager import fund_manager


def _mock_approve_response() -> str:
    return json.dumps(
        {"decision": "approve", "reasoning": "风险可控，建议执行"},
        ensure_ascii=False,
    )


def _mock_return_response() -> str:
    return json.dumps(
        {"decision": "return", "reasoning": "仓位过重，建议调整"},
        ensure_ascii=False,
    )


class TestFundManager:
    """Layer V Fund Manager Agent。"""

    @patch("finance_agent.nodes.fund_manager.call_llm")
    def test_approve_decision(self, mock_llm):
        mock_llm.return_value = _mock_approve_response()
        state = {
            "final_trade_decision": {
                "action": "buy",
                "confidence": 0.75,
                "reasoning": "...",
            },
            "return_count": 0,
        }
        result = fund_manager(state)
        assert result["fund_manager_decision"] == "approve"

    @patch("finance_agent.nodes.fund_manager.call_llm")
    def test_return_decision(self, mock_llm):
        mock_llm.return_value = _mock_return_response()
        state = {
            "final_trade_decision": {
                "action": "buy",
                "confidence": 0.75,
                "reasoning": "...",
            },
            "return_count": 0,
        }
        result = fund_manager(state)
        assert result["fund_manager_decision"] == "return"
        assert result["return_count"] == 1
