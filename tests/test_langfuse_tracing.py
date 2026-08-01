"""langfuse_tracing.open_span 单元测试。

验证 open_span 在三种场景下的行为：
1. Langfuse 已配置时创建 span
2. Langfuse 未配置时优雅降级返回 None
3. span 创建异常时降级不影响业务
"""

from unittest.mock import MagicMock, patch

from finance_agent.langfuse_tracing import open_span


class TestOpenSpan:
    """open_span 优雅降级测试。"""

    def test_langfuse_configured_creates_span(self):
        """Langfuse 已配置时调用 start_as_current_observation 创建 span。"""
        mockClient = MagicMock()
        mockCm = MagicMock()
        mockObs = MagicMock()
        mockClient.start_as_current_observation.return_value = mockCm
        mockCm.__enter__.return_value = mockObs

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            open_span("tool:web_search", {"args": {"query": "test"}}) as obs,
        ):
            # 在 span 上下文内，obs 是 observation 对象
            assert obs is mockObs

        # 验证 start_as_current_observation 被正确调用
        mockClient.start_as_current_observation.assert_called_once_with(
            name="tool:web_search", as_type="span", input={"args": {"query": "test"}}
        )
        # 验证 span 上下文正确退出
        mockCm.__exit__.assert_called_once()

    def test_langfuse_not_configured_returns_none(self):
        """Langfuse 未配置时返回 None，不抛异常、不创建 span。"""
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
            open_span("tool:web_search", {"args": {}}) as obs,
        ):
            assert obs is None

    def test_span_creation_exception_degrades(self):
        """start_as_current_observation 抛异常时降级为 None，业务流程继续。"""
        mockClient = MagicMock()
        mockClient.start_as_current_observation.side_effect = RuntimeError("langfuse down")

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            open_span("tool:web_search", {"args": {}}) as obs,
        ):
            # 降级后 obs 为 None，但业务代码仍能继续执行
            assert obs is None

    def test_open_span_allows_output_update(self):
        """调用方可在 span 内用 obs.update 记录 output。"""
        mockClient = MagicMock()
        mockObs = MagicMock()
        mockClient.start_as_current_observation.return_value = MagicMock()
        mockClient.start_as_current_observation.return_value.__enter__.return_value = mockObs

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            open_span("tool:echo", {"args": {"text": "hi"}}) as obs,
        ):
            if obs:
                obs.update(output={"result": "echo: hi"})

        mockObs.update.assert_called_once_with(output={"result": "echo: hi"})
