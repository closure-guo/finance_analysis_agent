# tests/llm/test_gateway_stream.py
"""gateway 流式/工具入口测试（delta 5.1 后半）。

complete_stream / complete_with_tools 是 legacy 转调 gateway 的前提。
用 mock raw_stream/raw_completion 验证归一事件流与工具守卫。
"""

from __future__ import annotations

from finance_agent.llm.gateway import complete_stream


from types import SimpleNamespace, MethodType


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
        kinds = [e.kind for e in complete_stream([{"role": "user", "content": "hi"}], llm_config={"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"})]
        assert "reasoning" in kinds
        assert "text" in kinds


def sets_all_text(events):
    return "".join(e.text for e in events if e.kind == "text")
