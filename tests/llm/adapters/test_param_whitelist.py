"""Task 8（drop_params 白名单化）测试。

- glm（reasoning_forced）+ temperature → adapter 白名单剔除（不再依赖全局 drop）
- deepseek + temperature → 透传
- top_p 全场景透传（白名单内但无 capability 信号，YAGNI 保留）
- 白名单外未知参数透传至 litellm（由 litellm 原生报错，不静默丢弃）
- LLM_DROP_PARAMS_STRICT=1 回滚开关恢复全局 drop
"""

from __future__ import annotations

import logging

import pytest

from finance_agent.llm.adapters import litellm_adapter
from finance_agent.llm.adapters.litellm_adapter import (
    _drop_unsupported,
    raw_completion,
)


def _capture(monkeypatch: pytest.MonkeyPatch, calls: list[dict]) -> None:
    class _FakeResp:
        pass

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return _FakeResp()

    monkeypatch.setattr(litellm_adapter, "ensure_litellm_runtime", lambda: None)
    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)


def test_glm_temperature_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    _capture(monkeypatch, calls)
    raw_completion(
        model="openai/glm-5.2", messages=[{"role": "user", "content": "hi"}], temperature=0.3
    )
    assert calls, "litellm.completion should have been called"
    assert "temperature" not in calls[0]


def test_deepseek_temperature_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    _capture(monkeypatch, calls)
    raw_completion(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.3,
    )
    assert calls[0].get("temperature") == 0.3


def test_top_p_passed_through_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    _capture(monkeypatch, calls)
    raw_completion(model="openai/glm-5.2", messages=[{"role": "user", "content": "hi"}], top_p=0.9)
    raw_completion(
        model="deepseek/deepseek-chat", messages=[{"role": "user", "content": "hi"}], top_p=0.9
    )
    assert calls[0].get("top_p") == 0.9
    assert calls[1].get("top_p") == 0.9


def test_unknown_param_reaches_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    _capture(monkeypatch, calls)
    raw_completion(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
        totally_unknown_param="x",
    )
    assert calls[0].get("totally_unknown_param") == "x"


def test_drop_warning_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="finance_agent.llm.adapters.litellm_adapter"):
        out = _drop_unsupported({"model": "openai/glm-5.2", "temperature": 0.3})
    assert "temperature" not in out
    assert any("白名单剔除" in r.message for r in caplog.records)


def test_strict_env_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    monkeypatch.setattr(litellm_adapter, "_initialized", False)
    monkeypatch.setenv("LLM_DROP_PARAMS_STRICT", "1")
    litellm_adapter.ensure_litellm_runtime()
    assert litellm.drop_params is True

    # unset → False（回滚开关关闭后恢复白名单行为）
    monkeypatch.setattr(litellm_adapter, "_initialized", False)
    monkeypatch.delenv("LLM_DROP_PARAMS_STRICT", raising=False)
    try:
        litellm_adapter.ensure_litellm_runtime()
        assert litellm.drop_params is False
    finally:
        litellm.drop_params = False
        monkeypatch.setattr(litellm_adapter, "_initialized", False)
