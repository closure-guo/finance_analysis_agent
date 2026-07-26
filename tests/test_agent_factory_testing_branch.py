"""agent_factory._make_llm_client 的 TESTING 分支占位测试。"""

import os
from unittest.mock import patch


class TestMakeLlmClientTestingBranch:
    """_make_llm_client 在 TESTING 模式下的行为。"""

    def test_testing_mode_does_not_create_real_litellm_client(self):
        """TESTING=1 时不创建真实 LiteLLMClient（避免连真 LLM）。

        F2 只验证分支存在且不连真 LLM；F3 会替换为 stub 客户端。
        """
        with patch.dict(os.environ, {"TESTING": "1"}):
            # 重新 import 以触发 TESTING 常量读取
            import importlib

            import finance_agent.api as api_module

            importlib.reload(api_module)

            import finance_agent.agent_factory as factory

            importlib.reload(factory)

            # 调用 _make_llm_client，应走 TESTING 分支（占位 return None）
            # 而非创建真实 LiteLLMClient
            client = factory._make_llm_client("deepseek/test", "fake-key")
            # F2 占位：client 应为 None（或占位对象），不应是 LiteLLMClient 实例
            assert client is None or "LiteLLMClient" not in type(client).__name__

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
