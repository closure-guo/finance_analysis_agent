"""build_agent 工厂函数测试。

验证三种模式的 Agent 配置：工具集、max_iterations、system prompt。
"""

from finance_agent.agent_factory import build_agent


class TestBuildAgentQuick:
    """快速模式 Agent 配置。"""

    def test_returns_agent_instance(self):
        """build_agent 返回 Agent 实例。"""
        agent = build_agent(mode="quick", api_key="test-key")
        assert agent is not None

    def test_quick_mode_has_web_search_tool(self):
        """快速模式暴露 web_search 工具。"""
        agent = build_agent(mode="quick", api_key="test-key")
        tool_names = agent.tools.get_tool_names()
        assert "web_search" in tool_names

    def test_quick_mode_does_not_have_deep_analysis(self):
        """快速模式不暴露 run_deep_analysis 工具。"""
        agent = build_agent(mode="quick", api_key="test-key")
        tool_names = agent.tools.get_tool_names()
        assert "run_deep_analysis" not in tool_names

    def test_quick_mode_max_iterations_is_3(self):
        """快速模式 max_iterations=3。"""
        agent = build_agent(mode="quick", api_key="test-key")
        assert agent.max_iterations == 3


class TestBuildAgentDeep:
    """深度模式 Agent 配置。"""

    def test_returns_agent_instance(self):
        """build_agent 返回 Agent 实例。"""
        agent = build_agent(mode="deep", api_key="test-key")
        assert agent is not None

    def test_deep_mode_has_search_stock(self):
        """深度模式暴露 search_stock 工具。"""
        agent = build_agent(mode="deep", api_key="test-key")
        tool_names = agent.tools.get_tool_names()
        assert "search_stock" in tool_names

    def test_deep_mode_has_run_deep_analysis(self):
        """深度模式暴露 run_deep_analysis 工具。"""
        agent = build_agent(mode="deep", api_key="test-key")
        tool_names = agent.tools.get_tool_names()
        assert "run_deep_analysis" in tool_names

    def test_deep_mode_has_web_search(self):
        """深度模式暴露 web_search 工具。"""
        agent = build_agent(mode="deep", api_key="test-key")
        tool_names = agent.tools.get_tool_names()
        assert "web_search" in tool_names

    def test_deep_mode_max_iterations_is_10(self):
        """深度模式 max_iterations=10。"""
        agent = build_agent(mode="deep", api_key="test-key")
        assert agent.max_iterations == 10
