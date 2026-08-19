# tests/llm/test_llm_stream_thinshell.py
"""call_llm_stream 薄壳测试（delta 5.1-B2）。

双路径对拍：同一 raw_stream mock 下，legacy.call_llm_stream 的 tuple 流
与 gateway.complete_stream 的 CanonicalEvent 流拼接一致。
"""

from __future__ import annotations

from types import SimpleNamespace

import litellm
import pytest

from finance_agent.llm.gateway import complete_stream
from finance_agent.llm.legacy import call_llm_stream

_FULL_CFG = {
    "model": "deepseek/deepseek-chat",
    "baseUrl": "https://api.deepseek.com/v1",
    "apiKey": "k",
}


def _chunk(*, text: str = "", reasoning: str = "", finish: str | None = None):
    """构造 litellm 同步流 chunk 形态：choices[0].delta。"""
    delta = SimpleNamespace(
        reasoning_content=reasoning or None,
        content=text or None,
    )
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


def _fake_stream(*, reasoning: str = "思考", text: str = "答"):
    """返回 fresh-iterator 的 raw_stream 替身（多次调用各得新迭代器）。"""

    def fake(**kwargs):  # noqa: ARG001
        yield _chunk(reasoning=reasoning)
        yield _chunk(text=text, finish="stop")

    return fake


class TestDualPathParity:
    def test_tuple_stream_matches_gateway_events(self, monkeypatch):
        """双路径对拍：tuple 流拼接 == CanonicalEvent 流拼接。"""
        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", _fake_stream())

        legacy = list(call_llm_stream("hi", system="sys", llm_config=dict(_FULL_CFG)))
        events = list(
            complete_stream(
                [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                llm_config=dict(_FULL_CFG),
            )
        )
        thinking = "".join(t for kind, t in legacy if kind == "thinking")
        answer = "".join(t for kind, t in legacy if kind == "answer")
        assert thinking == "".join(e.reasoning for e in events if e.kind == "reasoning")
        assert answer == "".join(e.text for e in events if e.kind == "text")


class TestErrorReraise:
    def test_raw_stream_error_raises_retryable_llm_error(self, monkeypatch):
        """raw_stream 抛 litellm 连接错误 → 薄壳重抛 LLMTimeoutError（retryable）。"""

        def fake(**kwargs):  # noqa: ARG001
            raise litellm.exceptions.APIConnectionError(
                message="boom", llm_provider="openai", model="x"
            )
            yield  # pragma: no cover

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake)
        with pytest.raises(Exception) as ei:  # noqa: PT011
            list(call_llm_stream("hi", llm_config=dict(_FULL_CFG)))
        from finance_agent.llm.errors import LLMError, LLMTimeoutError

        assert isinstance(ei.value, LLMError)
        assert isinstance(ei.value, LLMTimeoutError)
        assert ei.value.retryable is True


class TestDeprecation:
    def test_warns_deprecation(self, monkeypatch):
        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", _fake_stream())
        with pytest.warns(DeprecationWarning):
            list(call_llm_stream("hi", llm_config=dict(_FULL_CFG)))


class TestHalfConfig:
    def test_incomplete_request_config_raises(self, monkeypatch):
        """半套配置（只有 model，无 env 兜底）→ IncompleteLLMConfigError 透传。"""
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        from finance_agent.llm.resolver import IncompleteLLMConfigError

        with pytest.raises(IncompleteLLMConfigError):
            list(call_llm_stream("hi", llm_config={"model": "openai/gpt-4o-mini"}))
