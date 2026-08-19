# tests/llm/test_gateway_stream.py
"""gateway 流式/工具入口测试（delta 5.1 后半）。

complete_stream / complete_with_tools 是 legacy 转调 gateway 的前提。
用 mock raw_stream/raw_completion 验证归一事件流与工具守卫。
"""

from __future__ import annotations

from types import SimpleNamespace

from finance_agent.llm.gateway import complete_stream


def _chunk(*, text: str = "", reasoning: str = "", finish: str | None = None):
    """构造 litellm 同步流 chunk 形态：choices[0].delta。"""
    delta = SimpleNamespace(
        reasoning_content=reasoning or None,
        content=text or None,
    )
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


class TestCompleteStream:
    def test_yields_text_events(self, monkeypatch):

        captured = []

        def fake_stream(**kwargs):  # noqa: ARG001
            captured.append(kwargs)
            yield _chunk(text="你")
            yield _chunk(text="好")
            yield _chunk(finish="stop")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        events = []
        for ev in complete_stream(
            [{"role": "user", "content": "hi"}],
            llm_config={"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"},
        ):
            events.append(ev)
            # raw_stream 内部固定 stream=True，此处仅验证请求构造已下发
            assert captured[0]["model"] == "openai/glm-5.2"
        kinds = [e.kind for e in events]
        assert "text" in kinds
        assert "finished" in kinds

    def test_yields_reasoning_events(self, monkeypatch):
        def fake_stream(**kwargs):  # noqa: ARG001
            yield _chunk(reasoning="思考过程")
            yield _chunk(text="答", finish="stop")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        kinds = [
            e.kind
            for e in complete_stream(
                [{"role": "user", "content": "hi"}],
                llm_config={"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"},
            )
        ]
        assert "reasoning" in kinds
        assert "text" in kinds


class TestCompleteStreamTemperatureAndProviderOptions:
    def _run(self, monkeypatch, llm_config, *, temperature=None):
        captured = []

        def fake_stream(**kwargs):
            captured.append(kwargs)
            yield _chunk(text="答", finish="stop")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        list(
            complete_stream(
                [{"role": "user", "content": "hi"}],
                llm_config=llm_config,
                temperature=temperature,
            )
        )
        return captured[0]

    def test_temperature_passed_through(self, monkeypatch):
        kw = self._run(
            monkeypatch,
            {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"},
            temperature=0.3,
        )
        assert kw["temperature"] == 0.3

    def test_no_temperature_when_not_given(self, monkeypatch):
        kw = self._run(
            monkeypatch,
            {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"},
        )
        assert "temperature" not in kw

    def test_deepseek_provider_kwargs_and_suppressed_temperature(self, monkeypatch):
        """deepseek thinking=enabled：extra_body/reasoning_effort 下发，不发 temperature。"""
        kw = self._run(
            monkeypatch,
            {
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            },
            temperature=0.7,
        )
        assert kw["extra_body"] == {"thinking": {"type": "enabled"}}
        assert kw["reasoning_effort"] == "max"
        assert "suppress_temperature" not in kw
        assert "temperature" not in kw

    def test_deepseek_thinking_disabled_still_sends_temperature(self, monkeypatch):
        kw = self._run(
            monkeypatch,
            {
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
                "thinking": "disabled",
            },
            temperature=0.7,
        )
        assert kw["extra_body"] == {"thinking": {"type": "disabled"}}
        assert kw["temperature"] == 0.7


def sets_all_text(events):
    return "".join(e.text for e in events if e.kind == "text")


class TestCompleteStreamObservation:
    def test_trace_updates_generation(self, monkeypatch):
        """观测收口：传 trace 时 generation 结束前 update answer/reasoning。"""
        updated = {}

        class _FakeObs:
            def update(self, **kw):
                updated.update(kw)

        class _FakeCM:
            def __enter__(self):
                return _FakeObs()

            def __exit__(self, *a):
                return False

        got = {}

        class _FakeLF:
            def start_as_current_observation(self, **kw):
                got["name"] = kw.get("name")
                got["metadata"] = kw.get("metadata")
                return _FakeCM()

        monkeypatch.setattr("finance_agent.langfuse_tracing.get_langfuse", lambda: _FakeLF())

        def fake_stream(**kwargs):  # noqa: ARG001
            yield _chunk(reasoning="思")
            yield _chunk(text="答", finish="stop")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        events = list(
            complete_stream(
                [{"role": "user", "content": "hi"}],
                llm_config={"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"},
                trace={"name": "react_agent", "metadata": {"agent": "react"}},
            )
        )
        assert any(e.kind == "text" for e in events)
        assert got["name"] == "react_agent"
        assert updated["output"]["answer"] == "答"
        assert updated["output"]["reasoning"] == "思"
