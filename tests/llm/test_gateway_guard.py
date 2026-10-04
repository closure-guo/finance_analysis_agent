# tests/llm/test_gateway_guard.py
"""complete_text 纯文本交付物 guard 契约（delta add-output-contract-guard）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finance_agent.llm.errors import OutputTruncatedError
from finance_agent.llm.gateway import complete_text

_LEAKED = (
    "The user wants a 150-200 character research focus summary for 拓荆科技.\n\n"
    "Key points to weave in:\n\nDraft:\n\n“综合裁决为中性……PE_ttm 85."
)
_LLM_CFG = {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"}


def _fake_completion(content: str, finish_reason: str = "stop"):
    def fake(**kwargs):  # noqa: ARG001
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, reasoning_content=None),
                    finish_reason=finish_reason,
                )
            ],
            usage=None,
        )

    return fake


def test_guard_pass_clean_text(monkeypatch):
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("中远海能多空证据大体均衡，给予中性评级，维持观望。"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
    )
    assert meta["guard"]["ok"] is True
    assert meta["finish_reason"] == "stop"


def test_guard_flags_leak(monkeypatch):
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion(_LEAKED),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
    )
    assert meta["guard"]["ok"] is False
    assert "leak:the_user_wants" in meta["guard"]["hits"]


def test_guard_flags_length_finish(monkeypatch):
    """guard 的 length 分支接缝测试（裁决 A）。

    resume 机制（llm-output-resume 完整性层契约）正常会拦截 finish=length
    触发续写，真实生产路径中 length 由 resume 层处置；本测试用接缝绕过
    （monkeypatch _maybe_resume_text 为 False）以单独验证 length 信号到达
    guard 判定时能正确产出 truncated:length。
    """

    monkeypatch.setattr("finance_agent.llm.gateway._maybe_resume_text", lambda f, a: False)
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("完全合规的中文摘要，以句号收尾。", finish_reason="length"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
    )
    assert meta["guard"]["ok"] is False
    assert "truncated:length" in meta["guard"]["hits"]


def test_no_guard_param_no_guard_key(monkeypatch):
    """向后兼容：不传 output_guard 时返回 metadata 无 guard 键。"""
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("干净的中文摘要。"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}], purpose="quick", llm_config=_LLM_CFG
    )
    assert "guard" not in meta


def test_observation_metadata_carries_finish_reason_and_guard(monkeypatch):
    """spec «判定结果可观测»：观测 metadata 落 finish_reason/resume_count/guard。"""
    updates = []

    class _FakeObs:
        def update(self, **kw):
            updates.append(kw)

    class _FakeCM:
        def __enter__(self):
            return _FakeObs()

        def __exit__(self, *a):
            return False

    class _FakeLF:
        def start_as_current_observation(self, **kw):  # noqa: ARG002
            return _FakeCM()

    monkeypatch.setattr("finance_agent.langfuse_tracing.get_langfuse", lambda: _FakeLF())
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion(_LEAKED),
    )
    complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
        trace={"name": "report", "metadata": {"agent": "report"}},
    )
    metas = [u["metadata"] for u in updates if "metadata" in u]
    last = metas[-1]
    assert last["finish_reason"] == "stop"
    assert last["resume_count"] == 0
    assert last["guard"]["ok"] is False


# ---- 观测替身（合并式 metadata 断言用，shape 对齐 test_gateway_resume.py）----


class _Obs:
    def __init__(self, updates):
        self._updates = updates

    def update(self, **kw):
        self._updates.append(kw)


class _ObsCM:
    def __init__(self, updates):
        self._updates = updates

    def __enter__(self):
        return _Obs(self._updates)

    def __exit__(self, *a):
        return False


class _ObsLF:
    def __init__(self, updates):
        self._updates = updates

    def start_as_current_observation(self, **kw):  # noqa: ARG002
        return _ObsCM(self._updates)


def _fake_length_completion(content: str):
    """每次调用都返回 finish_reason=length（正文非空）的 raw_completion 替身。"""

    def fake(**kwargs):  # noqa: ARG001
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, reasoning_content=None),
                    finish_reason="length",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    return fake


def test_truncated_error_observation_merges_metadata(monkeypatch):
    """Task2-a：OutputTruncatedError 路径观测合并式——error_type/truncated/
    resume_count/finish_reason 同落在最终 metadata（整体替换会丢内层已写信号）。"""
    updates = []
    monkeypatch.setattr("finance_agent.langfuse_tracing.get_langfuse", lambda: _ObsLF(updates))
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_length_completion("前半"),
    )
    with pytest.raises(OutputTruncatedError):
        complete_text(
            [{"role": "user", "content": "hi"}],
            purpose="quick",
            llm_config=_LLM_CFG,
            trace={"name": "report", "metadata": {"agent": "report"}},
        )
    metas = [u["metadata"] for u in updates if "metadata" in u]
    last = metas[-1]
    assert last["error_type"] == "OutputTruncatedError"
    assert last["truncated"] is True
    assert last["resume_count"] == 1
    assert last["finish_reason"] == "length"


def test_guard_empty_dict_defaults_zh(monkeypatch):
    """Task2-b：output_guard={} 空 dict → target_lang 缺省 zh，guard 仍生效。"""
    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion",
        _fake_completion("中远海能多空证据大体均衡，给予中性评级，维持观望。"),
    )
    _, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={},
    )
    assert meta["guard"]["ok"] is True


def test_guard_validates_concatenated_text_after_resume(monkeypatch):
    """guard-after-resume（incident 036 邻近场景）：续写拼接后 guard 校验全文。"""
    updates = []
    monkeypatch.setattr("finance_agent.langfuse_tracing.get_langfuse", lambda: _ObsLF(updates))
    calls = []

    def fake_raw_completion(**kwargs):  # noqa: ARG001
        calls.append(kwargs)
        if len(calls) == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="多空证据大体均衡，", reasoning_content=None
                        ),
                        finish_reason="length",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="给予中性评级，维持观望。", reasoning_content=None
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_completion", fake_raw_completion
    )
    text, meta = complete_text(
        [{"role": "user", "content": "hi"}],
        purpose="quick",
        llm_config=_LLM_CFG,
        output_guard={"target_lang": "zh"},
        trace={"name": "report", "metadata": {"agent": "report"}},
    )
    assert text == "多空证据大体均衡，给予中性评级，维持观望。"
    assert meta["guard"]["ok"] is True
    assert meta["finish_reason"] == "stop"
    assert meta["resume_count"] == 1
    metas = [u["metadata"] for u in updates if "metadata" in u]
    last = metas[-1]
    assert last["resume_count"] == 1
    assert last["guard"]["ok"] is True
