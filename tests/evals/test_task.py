# tests/evals/test_task.py
"""run_task:mode 分派、输出可序列化、follow_up 跳过、graph 配置。"""

import json
from unittest.mock import MagicMock, patch

from evals.task import run_task


class _Item:
    def __init__(self, input_):
        self.input = input_


class TestDeepTask:
    @patch("evals.task.build_5layer_graph")
    def test_deep_invokes_graph_and_extracts(self, mock_build):
        final_state = {
            "final_report": "## 结论\n买入。",
            "analyst_reports": {},
            "debate_history": [],
            "research_manager_conclusion": "rm",
            "final_trade_decision": {"action": "buy"},
            "risk_debate_history": [],
            "fund_manager_decision": "approve",
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = final_state
        mock_build.return_value = mock_graph

        out = run_task(
            item=_Item(
                {
                    "query": "分析茅台",
                    "mode": "deep",
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                }
            )
        )
        assert out["report"] == "## 结论\n买入。"
        assert out["ticker"] == "600519"
        assert out["mode"] == "deep"
        assert out["skipped"] is None
        assert "买入" in out["judge_vars"]["report_conclusion"]
        # 序列化铁律:不得含 DataFrame 等不可序列化对象
        json.dumps(out)
        # initial_state 关键键
        state_arg = mock_graph.invoke.call_args.args[0]
        assert state_arg["stock_code"] == "600519"
        assert state_arg["enable_web_search"] is False


class TestQuickTask:
    @patch("evals.task.build_agent")
    def test_quick_runs_agent_sync(self, mock_build):
        agent = MagicMock()

        async def _run_sync(query):
            return "茅台是好公司"

        agent.run_sync = _run_sync
        mock_build.return_value = agent

        out = run_task(item=_Item({"query": "茅台怎么样", "mode": "quick", "ticker": "600519"}))
        assert out["report"] == "茅台是好公司"
        assert out["ticker"] == "600519"
        assert out["judge_vars"]["query"] == "茅台怎么样"
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["mode"] == "quick"
        json.dumps(out)


class TestSkippedModes:
    def test_follow_up_skipped(self):
        out = run_task(item=_Item({"query": "再分析下", "mode": "follow_up", "session_id": "s1"}))
        assert out["skipped"] is not None
        assert out["report"] is None
        json.dumps(out)

    def test_should_clarify_skipped(self):
        out = run_task(
            item=_Item({"query": "帮我看看", "mode": "deep"}),
            expected_output={"should_clarify": True},
        )
        assert out["skipped"] is not None
        json.dumps(out)
