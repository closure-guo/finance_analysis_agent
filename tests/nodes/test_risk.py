"""TDD tests for nodes/risk.py — Layer IV Risk Management 辩论 + Judge。"""

import json
from unittest.mock import patch

from finance_agent.nodes.risk import (
    aggressive_debater,
    conservative_debater,
    neutral_debater,
    risk_judge,
)


def _mock_risk_msg(role: str) -> str:
    return json.dumps(
        {
            "role": role,
            "round": 1,
            "content": f"{role} 视角的风险分析",
            "key_arguments": ["论点1"],
        },
        ensure_ascii=False,
    )


def _mock_judge_response() -> str:
    return json.dumps(
        {
            "action": "buy",
            "confidence": 0.6,
            "reasoning": "风险可控，建议轻仓买入",
            "position_size": "light",
        },
        ensure_ascii=False,
    )


class TestRiskDebaters:
    """Layer IV 风险辩论 Agent。"""

    @patch("finance_agent.nodes.risk.call_llm_streaming")
    def test_aggressive_debater(self, mock_llm):
        mock_llm.return_value = _mock_risk_msg("aggressive")
        result = aggressive_debater({"risk_debate_history": [], "trader_plan": {}})
        msg = result["risk_debate_history"][0]
        assert msg.role == "aggressive"

    @patch("finance_agent.nodes.risk.call_llm_streaming")
    def test_conservative_debater(self, mock_llm):
        mock_llm.return_value = _mock_risk_msg("conservative")
        result = conservative_debater({"risk_debate_history": [], "trader_plan": {}})
        msg = result["risk_debate_history"][0]
        assert msg.role == "conservative"

    @patch("finance_agent.nodes.risk.call_llm_streaming")
    def test_neutral_debater(self, mock_llm):
        mock_llm.return_value = _mock_risk_msg("neutral")
        result = neutral_debater({"risk_debate_history": [], "trader_plan": {}})
        msg = result["risk_debate_history"][0]
        assert msg.role == "neutral"


class TestRiskJudge:
    """Layer IV Risk Judge — 最终交易决策。"""

    @patch("finance_agent.nodes.risk.call_llm_streaming")
    def test_produces_final_decision(self, mock_llm):
        mock_llm.return_value = _mock_judge_response()
        state = {
            "trader_plan": {"action": "buy", "confidence": 0.75},
            "risk_debate_history": [],
        }
        result = risk_judge(state)
        assert "final_trade_decision" in result
        decision = result["final_trade_decision"]
        assert decision.action == "buy"
        assert decision.confidence == 0.6
