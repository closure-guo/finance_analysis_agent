# tests/nodes/test_call_llm_streaming_gateway.py
"""migrate-off-legacy-llm-shim Task 2：call_llm_streaming 直连 gateway.complete_stream。

mock 目标改为 ``finance_agent.llm.gateway.complete_stream``（原 mock
``finance_agent.llm.call_llm_stream`` 的用例迁移至此），断言 CanonicalEvent
迭代协议逐字节复刻：
- reasoning → thinking（经 stream writer）、text → answer 拼接、finished 忽略
- error 事件按 finish_reason（typed 类名字符串）还原为对应错误；查不到用 UnknownLLMError
- error(OutputTruncatedError) → 131072 预算复核翻倍重试（截断续写 fallback 保留）
- retryable 非截断错误重试一次，预算不翻倍（escalate 仅截断分支触发）
- 不再经 legacy call_llm_stream（TDD 红锚点）
"""

from unittest.mock import MagicMock, patch

import pytest

_STREAM = "finance_agent.llm.gateway.complete_stream"


class TestLegacyNotUsed:
    def test_call_llm_streaming_uses_gateway_directly(self):
        """迁移锚点：call_llm_streaming 直连 gateway.complete_stream。

        migrate-off-legacy-llm-shim Task 3 收尾：legacy 薄壳已删除，不再有
        包级 call_llm_stream 可被调用；断言直连 gateway 路径不变。
        """
        from finance_agent.llm.types import CanonicalEvent

        with patch(_STREAM) as mock_stream:
            mock_stream.return_value = iter([CanonicalEvent(kind="text", text="ok")])
            from finance_agent.nodes._llm_utils import call_llm_streaming

            assert call_llm_streaming("p", node_name="trader") == "ok"
            mock_stream.assert_called_once()

    def test_legacy_call_llm_stream_symbol_gone(self):
        """包级 call_llm_stream 已移除（Task 3 删除 legacy re-export）。"""
        import finance_agent.llm as llm_pkg

        assert not hasattr(llm_pkg, "call_llm_stream")


class TestCanonicalEventMapping:
    def test_concatenates_answer_and_skips_finished(self):
        from finance_agent.llm.types import CanonicalEvent

        with patch(_STREAM) as mock_stream:
            mock_stream.return_value = iter(
                [
                    CanonicalEvent(kind="reasoning", reasoning="思考A"),
                    CanonicalEvent(kind="text", text="答一"),
                    CanonicalEvent(kind="finished", finish_reason="stop"),
                    CanonicalEvent(kind="text", text="答二"),
                ]
            )
            from finance_agent.nodes._llm_utils import call_llm_streaming

            assert call_llm_streaming("p", node_name="trader") == "答一答二"

    def test_thinking_goes_to_stream_writer(self):
        from finance_agent.llm.types import CanonicalEvent

        writer = MagicMock()
        with (
            patch(_STREAM) as mock_stream,
            patch("langgraph.config.get_stream_writer", return_value=writer),
        ):
            mock_stream.return_value = iter(
                [
                    CanonicalEvent(kind="reasoning", reasoning="思考"),
                    CanonicalEvent(kind="text", text="答"),
                ]
            )
            from finance_agent.nodes._llm_utils import call_llm_streaming

            call_llm_streaming("p", node_name="trader")

        writer.assert_called_once_with({"type": "thinking", "node": "trader", "token": "思考"})

    def test_thinking_without_writer_is_dropped(self):
        from finance_agent.llm.types import CanonicalEvent

        with patch(_STREAM) as mock_stream:
            mock_stream.return_value = iter(
                [
                    CanonicalEvent(kind="reasoning", reasoning="思考"),
                    CanonicalEvent(kind="text", text="答"),
                ]
            )
            from finance_agent.nodes._llm_utils import call_llm_streaming

            assert call_llm_streaming("p", node_name="trader") == "答"


class TestErrorEventRestore:
    def test_error_event_restores_typed_error_and_raises(self):
        """error 事件按 finish_reason（类名）还原 typed error 并上抛（重试耗尽后）。"""
        from finance_agent.llm.errors import OutputTruncatedError
        from finance_agent.llm.types import CanonicalEvent

        def fake(*a, **kw):  # noqa: ARG001
            return iter(
                [
                    CanonicalEvent(
                        kind="error",
                        finish_reason="OutputTruncatedError",
                        raw={"error": "finish_reason=length"},
                    )
                ]
            )

        with (
            patch(_STREAM, side_effect=fake),
            pytest.raises(OutputTruncatedError, match="finish_reason=length"),
        ):
            from finance_agent.nodes._llm_utils import call_llm_streaming

            call_llm_streaming("p", node_name="trader")

    def test_error_event_triggers_budget_escalation_retry(self):
        """截断续写 fallback 保留：首次 error(OutputTruncatedError) → max_tokens 翻倍至 131072 重试。"""
        from finance_agent.llm.types import CanonicalEvent

        captured = []

        def fake(*a, **kw):
            captured.append(kw.get("max_tokens"))
            if len(captured) == 1:
                return iter(
                    [
                        CanonicalEvent(
                            kind="error",
                            finish_reason="OutputTruncatedError",
                            raw={"error": "finish_reason=length"},
                        )
                    ]
                )
            return iter([CanonicalEvent(kind="text", text="ok")])

        with patch(_STREAM, side_effect=fake):
            from finance_agent.nodes._llm_utils import call_llm_streaming

            assert call_llm_streaming("p", node_name="trader") == "ok"
        assert captured == [65536, 131072]

    def test_retryable_non_truncated_error_retries_without_escalation(self):
        """retryable 非截断（EmptyLLMOutputError）重试一次，预算不翻倍（escalate 仅截断分支触发）。"""
        from finance_agent.llm.types import CanonicalEvent

        calls = {"n": 0, "max_tokens": []}

        def fake(*a, **kw):
            calls["n"] += 1
            calls["max_tokens"].append(kw.get("max_tokens"))
            if calls["n"] == 1:
                return iter(
                    [
                        CanonicalEvent(
                            kind="error",
                            finish_reason="EmptyLLMOutputError",
                            raw={"error": "thinking 后即止"},
                        )
                    ]
                )
            return iter([CanonicalEvent(kind="text", text="res")])

        with patch(_STREAM, side_effect=fake):
            from finance_agent.nodes._llm_utils import call_llm_streaming

            assert call_llm_streaming("p") == "res"
        assert calls["n"] == 2
        assert calls["max_tokens"] == [65536, 65536]

    def test_unknown_error_event_falls_back_to_unknown_llm_error(self):
        """finish_reason 查不到 typed 类 → UnknownLLMError 还原（对齐 legacy _ERROR_CLASS_BY_NAME 缺省）。"""
        from finance_agent.llm.errors import UnknownLLMError
        from finance_agent.llm.types import CanonicalEvent

        def fake(*a, **kw):  # noqa: ARG001
            return iter(
                [CanonicalEvent(kind="error", finish_reason="BogusClass", raw={"error": "bogus"})]
            )

        with (
            patch(_STREAM, side_effect=fake),
            pytest.raises(UnknownLLMError, match="bogus"),
        ):
            from finance_agent.nodes._llm_utils import call_llm_streaming

            call_llm_streaming("p")


class TestRequestConstruction:
    def test_builds_messages_and_request_dict(self):
        from finance_agent.llm.types import CanonicalEvent

        with patch(_STREAM) as mock_stream:
            mock_stream.return_value = iter([CanonicalEvent(kind="text", text="ok")])
            from finance_agent.nodes._llm_utils import call_llm_streaming

            call_llm_streaming("hi", system="你是助手", node_name="technical_analyst")

        args, kwargs = mock_stream.call_args
        assert args[0] == [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "hi"},
        ]
        assert kwargs["purpose"] == "deep"
        assert kwargs["max_tokens"] == 65536
        assert kwargs["temperature"] == 0.3
        assert kwargs["llm_config"] is None
        assert kwargs["trace"] == {
            "name": "technical_analyst",
            "metadata": {"agent": "technical_analyst"},
        }
