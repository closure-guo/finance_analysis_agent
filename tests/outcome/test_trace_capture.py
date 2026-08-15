"""fund_manager approve 时捕获 langfuse trace_id 入 state。"""

from unittest.mock import MagicMock, patch

import finance_agent.nodes.fund_manager as fm_mod


class TestTraceCapture:
    def _run_fund_manager(self):
        """驱动 fund_manager 节点,返回 state update。"""
        state = {
            "stock_code": "600519",
            "final_trade_decision": {
                "action": "buy",
                "confidence": 0.8,
                "reasoning": "x",
                "entry_price": None,
                "stop_loss": 90.0,
                "target_price": 120.0,
                "position_size": None,
            },
            "return_count": 0,
        }
        return fm_mod.fund_manager(state)

    @patch.object(fm_mod, "call_llm_streaming")
    def test_approve_captures_trace_id(self, mock_llm):
        mock_llm.return_value = '{"decision": "approve", "feedback": "ok"}'
        mock_client = MagicMock()
        mock_client.get_current_trace_id.return_value = "trace-xyz"
        with patch.object(fm_mod, "get_langfuse", return_value=mock_client):
            update = self._run_fund_manager()
        assert update["fund_manager_decision"] == "approve"
        assert update["langfuse_trace_id"] == "trace-xyz"

    @patch.object(fm_mod, "call_llm_streaming")
    def test_reject_no_trace_capture(self, mock_llm):
        mock_llm.return_value = '{"decision": "reject", "feedback": "no"}'
        with patch.object(fm_mod, "get_langfuse") as mock_get:
            update = self._run_fund_manager()
        assert update["fund_manager_decision"] == "reject"
        assert "langfuse_trace_id" not in update
        mock_get.assert_not_called()

    @patch.object(fm_mod, "call_llm_streaming")
    def test_langfuse_unconfigured_no_key(self, mock_llm):
        mock_llm.return_value = '{"decision": "approve", "feedback": "ok"}'
        with patch.object(fm_mod, "get_langfuse", return_value=None):
            update = self._run_fund_manager()
        assert "langfuse_trace_id" not in update  # 降级:不写键

    @patch.object(fm_mod, "call_llm_streaming")
    def test_trace_id_exception_still_returns_decision(self, mock_llm):
        """旁路铁律:get_current_trace_id 抛异常不阻断节点,仅 WARNING,不写键。"""
        mock_llm.return_value = '{"decision": "approve", "feedback": "ok"}'
        mock_client = MagicMock()
        mock_client.get_current_trace_id.side_effect = RuntimeError("otel weird")
        with patch.object(fm_mod, "get_langfuse", return_value=mock_client):
            update = self._run_fund_manager()
        assert update["fund_manager_decision"] == "approve"
        assert "langfuse_trace_id" not in update
