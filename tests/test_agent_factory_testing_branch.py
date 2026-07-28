"""agent_factory._make_llm_client 的 TESTING 分支测试。

F3a: TESTING=1 时返回 StubLLMClient（非 None 占位，非真实 LiteLLMClient）。
"""

import os
from unittest.mock import patch


class TestMakeLlmClientTestingBranch:
    """_make_llm_client 在 TESTING 模式下的行为。"""

    def test_testing_mode_returns_stub_llm_client(self):
        """TESTING=1 时返回 StubLLMClient 实例。

        F3a 替换了 F2 的 return None 占位，stub 客户端按固定节奏吐文本 delta。
        """
        with patch.dict(os.environ, {"TESTING": "1"}):
            # 重新 import 以触发 TESTING 常量读取
            import importlib

            import finance_agent.api as api_module

            importlib.reload(api_module)

            import finance_agent.agent_factory as factory

            importlib.reload(factory)

            from finance_agent.harness.stub_llm_client import StubLLMClient

            # 调用 _make_llm_client，应返回 StubLLMClient 实例
            client = factory._make_llm_client("deepseek/test", "fake-key")
            # 增强断言：必须是 StubLLMClient 类型（防止回退到 return None）
            assert isinstance(client, StubLLMClient), (
                f"期望 StubLLMClient，实际 {type(client).__name__}"
            )

    def test_normal_mode_creates_real_litellm_client(self):
        """非 TESTING 模式下创建真实 LiteLLMClient。"""
        env = {k: v for k, v in os.environ.items() if k != "TESTING"}
        with patch.dict(os.environ, env, clear=True):
            import importlib

            import finance_agent.api as api_module

            importlib.reload(api_module)

            import finance_agent.agent_factory as factory

            importlib.reload(factory)

            client = factory._make_llm_client("deepseek/test", "fake-key")
            # 正常模式下应创建 LiteLLMClient（或其包装）
            assert client is not None


class TestStubWebSearchTool:
    """TESTING=1 时注册的 stub web_search 工具。

    确定性返回固定搜索结果（format_search_for_llm 兼容格式），不调真实 Tavily，
    使 E2E 能在 TESTING=1 下确定性验证"思考->web search->思考"时间序列。
    """

    def test_stub_web_search_returns_parseable_fixed_results(self):
        """stub web_search 工具返回可被 parse_search_output 解析的固定结果。"""
        with patch.dict(os.environ, {"TESTING": "1", "STUB_SCENARIO": "tool_call"}):
            import importlib

            import finance_agent.api as api_module

            importlib.reload(api_module)
            import finance_agent.agent_factory as factory

            importlib.reload(factory)

            agent = factory.build_agent(mode="quick", api_key="fake-key")
            # 取出注册的 web_search 工具并执行
            import asyncio

            async def _run() -> str:
                result = await agent.tools.execute("call_1", "web_search", {"query": "茅台"})
                return result.output

            output = asyncio.run(_run())

            # 应返回 stub 固定标记（区别于真实搜索结果，锁定"TESTING=1 用 stub"行为）
            assert "STUB 搜索结果" in output, (
                f"TESTING=1 下 web_search 应返回 stub 固定标记，实际输出：{output[:100]}"
            )

            # 应可被 parse_search_output 解析
            from finance_agent.web_search import parse_search_output

            results = parse_search_output(output)
            assert len(results) >= 1, "stub web_search 应返回至少 1 条可解析的搜索结果"
            assert results[0].url.startswith("http"), "搜索结果应含有效 URL"

    def test_stub_web_search_does_not_call_real_tavily(self):
        """TESTING=1 时 stub web_search 不调用真实 Tavily API。"""
        with patch.dict(os.environ, {"TESTING": "1", "STUB_SCENARIO": "tool_call"}):
            import importlib

            import finance_agent.api as api_module

            importlib.reload(api_module)
            import finance_agent.agent_factory as factory

            importlib.reload(factory)

            agent = factory.build_agent(mode="quick", api_key="fake-key")

            # patch 真实 tavily_search 抛错：若 stub 仍正常返回，证明未走真实搜索
            import asyncio

            import finance_agent.web_search as ws

            def _forbidden(*args, **kwargs):
                raise AssertionError("TESTING=1 下不应调用真实 tavily_search")

            with patch.object(ws, "tavily_search", side_effect=_forbidden):

                async def _run() -> str:
                    result = await agent.tools.execute("call_1", "web_search", {"query": "茅台"})
                    return result.output

                output = asyncio.run(_run())
                # 真实搜索被禁后仍返回 stub 标记，证明走的是 stub 工具
                assert "STUB 搜索结果" in output, (
                    f"禁用真实 Tavily 后应仍返回 stub 标记，实际：{output[:100]}"
                )

    def test_deep_mode_stub_web_search_returns_stub_marker(self):
        """深度模式（build_agent(mode='deep')）在 TESTING=1 下也应注册 stub web_search。

        确定性复现"思考->web search->思考"时间序列时，deep 分支与 quick 分支
        应走同一 stub 逻辑，而非真实 Tavily（agent-turn-box-display delta task 5.4）。
        """
        with patch.dict(os.environ, {"TESTING": "1", "STUB_SCENARIO": "tool_call"}):
            import importlib

            import finance_agent.api as api_module

            importlib.reload(api_module)
            import finance_agent.agent_factory as factory

            importlib.reload(factory)

            agent = factory.build_agent(mode="deep", api_key="fake-key")

            import asyncio

            async def _run() -> str:
                result = await agent.tools.execute("call_1", "web_search", {"query": "茅台"})
                return result.output

            output = asyncio.run(_run())

            # 应返回 stub 固定标记（区别于真实搜索结果）
            assert "STUB 搜索结果" in output, (
                f"TESTING=1 下 deep 模式 web_search 应返回 stub 固定标记，实际输出：{output[:100]}"
            )
