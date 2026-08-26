# tests/llm/test_gateway_error_observability.py
"""gateway 错误观测对齐（601700/汉森制药复盘：Langfuse 只见 ERROR 不见原因）。

同步流式路径 complete_stream / 非流式 complete_text 的错误收口此前只写
``metadata.error_type``（类名），错误消息文本只进进程内 CanonicalEvent——
Langfuse UI 上 ERROR 级别旁空白，排障必须去翻被进度条搅乱的后端日志。
异步路径 complete_stream_async 已有 ``output={"error": str(err)}`` 写法，
本组测试钉住同步/非流式路径对齐：output.error + status_message 必须落观测。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finance_agent.llm.gateway import complete_stream, complete_text


def _chunk(*, text: str = "", reasoning: str = "", finish: str | None = None):
    delta = SimpleNamespace(reasoning_content=reasoning or None, content=text or None)
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


class _ObsRecorder:
    """伪 Langfuse observation：记录 update 调用。"""

    def __init__(self):
        self.updates: list[dict] = []

    def update(self, **kw):
        self.updates.append(kw)


def _install_fake_langfuse(monkeypatch) -> _ObsRecorder:
    rec = _ObsRecorder()

    class _FakeObs:
        def update(self, **kw):
            rec.updates.append(kw)

    class _FakeCM:
        def __enter__(self):
            return _FakeObs()

        def __exit__(self, *a):
            return False

    class _FakeLF:
        def start_as_current_observation(self, **kw):  # noqa: ARG002
            return _FakeCM()

    monkeypatch.setattr("finance_agent.langfuse_tracing.get_langfuse", lambda: _FakeLF())
    return rec


_LLM_CONFIG = {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"}
_TRACE = {"name": "technical_analyst", "metadata": {"agent": "technical_analyst"}}


def _last_update(rec: _ObsRecorder) -> dict:
    assert rec.updates, "generation 从未 update（观测缺失）"
    return rec.updates[-1]


class TestSyncStreamErrorObservability:
    def test_exception_writes_error_reason(self, monkeypatch):
        """raw_stream 抛异常 → output.error + status_message 落观测。"""

        def fake_stream(**kwargs):  # noqa: ARG001
            yield _chunk(text="部分")
            raise RuntimeError("boom 连接被重置")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        rec = _install_fake_langfuse(monkeypatch)

        events = list(
            complete_stream(
                [{"role": "user", "content": "hi"}], llm_config=_LLM_CONFIG, trace=_TRACE
            )
        )
        assert any(e.kind == "error" for e in events)

        final = _last_update(rec)
        assert final.get("level") == "ERROR"
        assert "连接被重置" in str(final.get("output", {}).get("error", "")), (
            f"错误消息须落 output.error: {final.get('output')}"
        )
        assert "连接被重置" in str(final.get("status_message", "")), (
            f"错误消息须落 status_message（Langfuse UI 错误原因列）: {final.get('status_message')}"
        )

    def test_truncation_writes_human_readable_reason(self, monkeypatch):
        """续写后仍截断 → status_message 人类可读说明，且部分正文不丢。"""
        calls = {"n": 0}

        def fake_stream(**kwargs):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                yield _chunk(text="第一段正文")
                yield _chunk(finish="length")
            else:  # 续写段仍截断
                yield _chunk(text="续写段")
                yield _chunk(finish="length")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        rec = _install_fake_langfuse(monkeypatch)

        events = list(
            complete_stream(
                [{"role": "user", "content": "hi"}], llm_config=_LLM_CONFIG, trace=_TRACE
            )
        )
        assert any(e.kind == "error" and e.finish_reason == "OutputTruncatedError" for e in events)

        final = _last_update(rec)
        assert final.get("level") == "ERROR"
        assert final.get("metadata", {}).get("truncated") is True
        assert "截断" in str(final.get("status_message", "")), (
            f"截断原因须可读落 status_message: {final.get('status_message')}"
        )
        # 部分正文已在观测 output 中，不得被 error 覆盖丢失
        outputs = [u.get("output") for u in rec.updates if u.get("output")]
        assert any("第一段正文" in str(o.get("answer", "")) for o in outputs), (
            f"部分正文不得因错误覆盖丢失: {outputs}"
        )

    def test_empty_output_writes_error_reason(self, monkeypatch):
        """流正常结束但零正文（classify_outcome 失败）→ 错误原因落观测。"""

        def fake_stream(**kwargs):  # noqa: ARG001
            yield _chunk(finish="stop")

        monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_stream", fake_stream)
        rec = _install_fake_langfuse(monkeypatch)

        events = list(
            complete_stream(
                [{"role": "user", "content": "hi"}], llm_config=_LLM_CONFIG, trace=_TRACE
            )
        )
        assert any(e.kind == "error" for e in events)

        final = _last_update(rec)
        assert final.get("level") == "ERROR"
        assert final.get("status_message"), "空输出失败须落可读原因"
        assert final.get("output", {}).get("error"), "空输出失败须落 output.error"


class TestCompleteTextErrorObservability:
    def test_exception_writes_error_reason(self, monkeypatch):
        """非流式异常 → output.error + status_message 落观测（对齐 async 路径）。"""

        def fake_completion(**kwargs):  # noqa: ARG001
            raise RuntimeError("quota exhausted")

        monkeypatch.setattr(
            "finance_agent.llm.adapters.litellm_adapter.raw_completion", fake_completion
        )
        rec = _install_fake_langfuse(monkeypatch)

        with pytest.raises(Exception, match="quota"):
            complete_text([{"role": "user", "content": "hi"}], llm_config=_LLM_CONFIG, trace=_TRACE)

        final = _last_update(rec)
        assert final.get("level") == "ERROR"
        assert "quota exhausted" in str(final.get("status_message", ""))
        assert "quota exhausted" in str(final.get("output", {}).get("error", ""))
