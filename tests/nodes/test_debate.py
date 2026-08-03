"""TDD tests for nodes/debate.py — Layer II Bull/Bear 辩论 Agent。"""

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from finance_agent.nodes.debate import bear_debater, bull_debater


def _mock_bull_response() -> str:
    return json.dumps(
        {
            "role": "bull",
            "round": 1,
            "content": "基于强劲的 ROE 增长和低负债率，建议买入",
            "key_arguments": ["ROE 28.33% 高于行业平均", "资产负债率仅 40%"],
        },
        ensure_ascii=False,
    )


def _mock_bear_response() -> str:
    return json.dumps(
        {
            "role": "bear",
            "round": 1,
            "content": "虽然基本面稳健，但估值过高，存在回调风险",
            "key_arguments": ["PE 处于历史 90 分位", "营收增速放缓"],
        },
        ensure_ascii=False,
    )


class TestBullDebater:
    """Layer II Bull 辩论 Agent。"""

    @patch("finance_agent.nodes.debate.call_llm_streaming")
    def test_produces_debate_message(self, mock_llm):
        mock_llm.return_value = _mock_bull_response()
        state = {
            "analyst_reports": {},
            "debate_history": [],
        }
        result = bull_debater(state)
        assert "debate_history" in result
        msg = result["debate_history"][0]
        assert msg.role == "bull"
        assert msg.round == 1
        assert len(msg.key_arguments) == 2


class TestBearDebater:
    """Layer II Bear 辩论 Agent。"""

    @patch("finance_agent.nodes.debate.call_llm_streaming")
    def test_produces_debate_message(self, mock_llm):
        mock_llm.return_value = _mock_bear_response()
        state = {
            "analyst_reports": {},
            "debate_history": [],
        }
        result = bear_debater(state)
        assert "debate_history" in result
        msg = result["debate_history"][0]
        assert msg.role == "bear"
        assert msg.round == 1


class TestDebateRoleValidation:
    """role 枚举约束（harden-llm-output-validation）。

    加固前 DebateMessage.role 是裸 str，LLM 串角色不会被发现，
    只会污染报告正文渲染与依赖 role 过滤的节点摘要提取。
    """

    @patch("finance_agent.nodes.debate.call_llm_streaming")
    def test_invalid_role_raises(self, mock_llm):
        """LLM 输出非法 role 时节点抛 ValidationError。"""
        mock_llm.return_value = json.dumps(
            {
                "role": "超级多头",
                "round": 1,
                "content": "内容",
                "key_arguments": ["论据"],
            },
            ensure_ascii=False,
        )
        with pytest.raises(ValidationError):
            bull_debater({"analyst_reports": {}, "debate_history": []})
