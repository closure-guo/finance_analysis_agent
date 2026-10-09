"""build_agent 工厂函数测试。

验证三种模式的 Agent 配置：工具集、max_iterations、system prompt。
"""

import inspect

from finance_agent.agent_factory import _make_run_deep_analysis, _resolve_peer_codes, build_agent


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


class TestRunDeepAnalysisPeerCodes:
    """run_deep_analysis 暴露 peer_codes 参数（add-peer-comparison）。

    LLM 显式传参优先于请求级闭包注入；归一化=strip/剔非 6 位数字/去重/
    剔主标的/上限 3。
    """

    def test_tool_signature_has_peer_codes(self):
        fn = _make_run_deep_analysis()
        sig = inspect.signature(fn)
        assert "peer_codes" in sig.parameters
        assert sig.parameters["peer_codes"].default is None

    def test_tool_docstring_documents_peer_codes(self):
        fn = _make_run_deep_analysis()
        assert "peer_codes" in (fn.__doc__ or "")

    def test_resolve_explicit_overrides_closure(self):
        assert _resolve_peer_codes(["000858"], ["601318"]) == ["000858"]
        assert _resolve_peer_codes(None, ["601318"]) == ["601318"]
        assert _resolve_peer_codes(None, None) is None
        assert _resolve_peer_codes([], None) is None

    def test_resolve_sanitizes_and_excludes_target(self):
        assert _resolve_peer_codes(
            [" 000858 ", "bad", "000858", "600519"], None, exclude="600519"
        ) == ["000858"]

    def test_resolve_caps_at_three(self):
        assert _resolve_peer_codes(["000001", "000002", "600000", "600519"], None) == [
            "000001",
            "000002",
            "600000",
        ]

    def test_resolve_tolerates_comma_joined_string(self):
        """schema string 类型容错：LLM 可能传逗号串，须切分而非逐字符校验。

        build_schema_from_function 对 list[str] | None 注解 fallback 为 JSON
        "string"，LLM 端实际可能发 "000858,600519" 这类逗号串。
        """
        assert _resolve_peer_codes("000858,600519", None, exclude="600519") == ["000858"]
        assert _resolve_peer_codes("000858， 601318", None) == ["000858", "601318"]

    def test_resolve_tolerates_json_array_string(self):
        """schema string 槽位下 LLM 高频把列表 JSON 序列化进字符串——须解析而非逐字符丢弃。"""
        assert _resolve_peer_codes('["000858","600519"]', None, exclude="600519") == ["000858"]
        assert _resolve_peer_codes('["000858", "601318"]', None) == ["000858", "601318"]

    def test_llm_schema_exposes_peer_codes(self):
        """工具 schema 对 LLM 可见 peer_codes（build_schema_from_function 从签名内省）。"""
        agent = build_agent(mode="deep", api_key="test-key")
        schemas = agent.tools.get_schemas_for_llm()
        rda = next(
            s
            for s in schemas
            if s.get("function", {}).get("name") == "run_deep_analysis"
            or s.get("name") == "run_deep_analysis"
        )
        params = rda.get("function", rda).get("parameters", {})
        assert "peer_codes" in params.get("properties", {})
