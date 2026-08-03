"""TDD tests for nodes/fund_manager.py — Layer V Fund Manager Agent。"""

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from finance_agent.nodes.fund_manager import fund_manager


def _mock_response(decision: str) -> str:
    """构造指定决策值的 LLM 响应。"""
    return json.dumps(
        {"decision": decision, "reasoning": "测试理由"},
        ensure_ascii=False,
    )


def _base_state() -> dict:
    return {
        "final_trade_decision": {
            "action": "buy",
            "confidence": 0.75,
            "reasoning": "...",
        },
        "return_count": 0,
    }


class TestFundManager:
    """Layer V Fund Manager Agent。"""

    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_approve_decision(self, mock_llm):
        mock_llm.return_value = _mock_response("approve")
        result = fund_manager(_base_state())
        assert result["fund_manager_decision"] == "approve"

    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_return_decision(self, mock_llm):
        mock_llm.return_value = _mock_response("return")
        result = fund_manager(_base_state())
        assert result["fund_manager_decision"] == "return"
        assert result["return_count"] == 1

    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_reject_decision(self, mock_llm):
        """reject 决策：不递增 return_count（此前缺失该用例）。"""
        mock_llm.return_value = _mock_response("reject")
        result = fund_manager(_base_state())
        assert result["fund_manager_decision"] == "reject"
        assert "return_count" not in result


class TestFundManagerValidation:
    """决策枚举强校验（harden-llm-output-validation）。

    加固前 `data["decision"]` 裸取键：非法值原样透传、缺键抛裸 KeyError，
    且非法值经 routing.py 的 else 分支被静默降级为 approve 语义。
    """

    @pytest.mark.parametrize("illegal", ["revise", "拒绝", "maybe", "APPROVED", ""])
    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_invalid_decision_raises(self, mock_llm, illegal):
        """非法决策值抛 ValidationError，不静默降级。"""
        mock_llm.return_value = _mock_response(illegal)
        with pytest.raises(ValidationError):
            fund_manager(_base_state())

    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_missing_decision_key_raises(self, mock_llm):
        """缺 decision 键抛 ValidationError（而非裸 KeyError）。"""
        mock_llm.return_value = json.dumps({"reasoning": "忘了给决策"}, ensure_ascii=False)
        with pytest.raises(ValidationError):
            fund_manager(_base_state())

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Approve", "approve"),
            ("APPROVE", "approve"),
            (" approve ", "approve"),
            ("Reject", "reject"),
            (" REJECT ", "reject"),
            ("Return", "return"),
            ("  RETURN  ", "return"),
        ],
    )
    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_decision_normalizes_case_and_whitespace(self, mock_llm, raw, expected):
        """大小写与首尾空白归一化后通过校验，写入 state 的是小写值。"""
        mock_llm.return_value = _mock_response(raw)
        result = fund_manager(_base_state())
        assert result["fund_manager_decision"] == expected

    @patch("finance_agent.nodes.fund_manager.call_llm_streaming")
    def test_normalized_return_increments_count(self, mock_llm):
        """归一化前的大小写变体同样触发 return_count 递增。"""
        mock_llm.return_value = _mock_response("Return")
        result = fund_manager(_base_state())
        assert result["fund_manager_decision"] == "return"
        assert result["return_count"] == 1
