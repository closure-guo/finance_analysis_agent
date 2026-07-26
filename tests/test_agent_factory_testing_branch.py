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
