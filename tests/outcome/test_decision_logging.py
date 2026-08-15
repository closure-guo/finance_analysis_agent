"""api._persist_decision_log:approve 落库、entry_price 回填、非 approve 跳过、失败不阻断。"""

from unittest.mock import patch

import pandas as pd

from finance_agent.api import _persist_decision_log


def _accumulated(**overrides):
    base = {
        "fund_manager_decision": "approve",
        "final_trade_decision": {
            "action": "buy",
            "confidence": 0.8,
            "reasoning": "x",
            "entry_price": None,
            "stop_loss": 90.0,
            "target_price": 120.0,
            "position_size": "30%",
        },
        "langfuse_trace_id": "trace-1",
        "stock_quote": {"price": 100.0},
    }
    base.update(overrides)
    return base


class TestPersistDecisionLog:
    @patch("finance_agent.api.insert_decision")
    def test_approve_inserts_with_quote_price(self, mock_insert):
        _persist_decision_log(_accumulated(), "sess-1", "600519", "贵州茅台")
        record = mock_insert.call_args.args[0]
        assert record["action"] == "buy"
        assert record["entry_price"] == 100.0  # quote 回填,非 LLM 的 None
        assert record["stop_loss"] == 90.0
        assert record["langfuse_trace_id"] == "trace-1"
        assert record["session_id"] == "sess-1"
        assert record["position_size"] is None  # "30%" 非数值 → None

    @patch("finance_agent.api.insert_decision")
    def test_kline_close_fallback(self, mock_insert):
        acc = _accumulated(stock_quote=None)
        acc["kline"] = pd.DataFrame([{"日期": "2026-08-01", "收盘": 99.5}])
        _persist_decision_log(acc, "sess-1", "600519", "茅台")
        assert mock_insert.call_args.args[0]["entry_price"] == 99.5

    @patch("finance_agent.api.insert_decision")
    def test_non_approve_skips(self, mock_insert):
        _persist_decision_log(_accumulated(fund_manager_decision="reject"), "s", "600519", "茅台")
        mock_insert.assert_not_called()
        _persist_decision_log(_accumulated(final_trade_decision=None), "s", "600519", "茅台")
        mock_insert.assert_not_called()

    @patch("finance_agent.api.insert_decision")
    def test_no_price_skips_with_warn(self, mock_insert, caplog):
        import logging

        acc = _accumulated(stock_quote=None, kline=None)
        with caplog.at_level(logging.WARNING):
            _persist_decision_log(acc, "s", "600519", "茅台")
        mock_insert.assert_not_called()
        assert any("entry_price" in r.message or "价格" in r.message for r in caplog.records)

    @patch("finance_agent.api.insert_decision", side_effect=RuntimeError("db down"))
    def test_failure_does_not_raise(self, mock_insert):
        # spec「落库失败不阻断业务」:异常吞掉记 ERROR
        _persist_decision_log(_accumulated(), "s", "600519", "茅台")  # 不抛
