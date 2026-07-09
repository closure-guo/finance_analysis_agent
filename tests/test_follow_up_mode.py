"""follow-up 模式测试。

验证追问模式正确加载 session 上下文并注入 system prompt。
"""

import json
from unittest.mock import patch

from finance_agent.agent_factory import build_agent


class TestBuildAgentFollowUp:
    """追问模式 Agent 配置测试。"""

    def test_follow_up_has_web_search_only(self):
        """追问模式只暴露 web_search 工具。"""
        mock_session = {
            "session_id": "test-123",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_markdown": "# 贵州茅台报告",
            "analyst_summaries": json.dumps({"technical": "看多"}),
            "chat_history": json.dumps([]),
        }

        with patch("finance_agent.session_store.get_session", return_value=mock_session):
            agent = build_agent(
                mode="follow-up",
                session_id="test-123",
                api_key="test-key",
            )

        tool_names = agent.tools.get_tool_names()
        assert "web_search" in tool_names
        assert "run_deep_analysis" not in tool_names
        assert "search_stock" not in tool_names

    def test_follow_up_max_iterations_is_3(self):
        """追问模式 max_iterations=3。"""
        mock_session = {
            "session_id": "test-123",
            "report_markdown": "# 报告",
            "analyst_summaries": "{}",
            "chat_history": "[]",
        }

        with patch("finance_agent.session_store.get_session", return_value=mock_session):
            agent = build_agent(
                mode="follow-up",
                session_id="test-123",
                api_key="test-key",
            )

        assert agent.max_iterations == 3

    def test_system_prompt_contains_report_content(self):
        """system prompt 包含报告内容。"""
        mock_session = {
            "session_id": "test-123",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_markdown": "# 贵州茅台深度分析报告\n\n## 毛利率分析\n毛利率 90%",
            "analyst_summaries": json.dumps({"technical": "技术面看多"}),
            "chat_history": json.dumps([]),
        }

        with patch("finance_agent.session_store.get_session", return_value=mock_session):
            agent = build_agent(
                mode="follow-up",
                session_id="test-123",
                api_key="test-key",
            )

        # system prompt 应该包含报告内容
        system_msg = agent.context.system_message.content
        assert "贵州茅台" in system_msg
        assert "毛利率" in system_msg

    def test_system_prompt_contains_chat_history(self):
        """system prompt 包含之前的对话历史。"""
        mock_session = {
            "session_id": "test-123",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_markdown": "# 报告",
            "analyst_summaries": "{}",
            "chat_history": json.dumps(
                [
                    {"role": "user", "content": "茅台的估值如何？"},
                    {"role": "assistant", "content": "茅台估值偏高"},
                ]
            ),
        }

        with patch("finance_agent.session_store.get_session", return_value=mock_session):
            agent = build_agent(
                mode="follow-up",
                session_id="test-123",
                api_key="test-key",
            )

        system_msg = agent.context.system_message.content
        assert "茅台的估值" in system_msg or "估值偏高" in system_msg

    def test_report_truncated_to_6000_chars(self):
        """报告超过 6000 字符时被截断。"""
        long_report = "# 报告\n" + "x" * 10000
        mock_session = {
            "session_id": "test-123",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report_markdown": long_report,
            "analyst_summaries": "{}",
            "chat_history": "[]",
        }

        with patch("finance_agent.session_store.get_session", return_value=mock_session):
            agent = build_agent(
                mode="follow-up",
                session_id="test-123",
                api_key="test-key",
            )

        system_msg = agent.context.system_message.content
        # 报告被截断，不应包含全部 10000 个 x
        assert system_msg.count("x") < 10000
        assert system_msg.count("x") <= 6100  # 6000 + 一些余量
