# tests/llm/test_budget_governance.py
"""预算治理（harden Task 5）：ContextBudget 按 capability 派生 + 观测字段。

- ContextBudget.from_capability：max_context 派生 / None 回落 120000
- calibrate：usage_total 真值翻转 usage_estimated 并上抬 max_context_tokens
- build_trace_metadata：max_tokens_source / usage_estimated 可选键（向后兼容）
- complete_text 返回 metadata 含 max_tokens_source（requested/capability 两态）
- async 错误路径观测 update 含 error_type
"""

from __future__ import annotations

from types import SimpleNamespace

import litellm
import pytest

from finance_agent.harness.context import ContextBudget
from finance_agent.llm.errors import LLMError
from finance_agent.llm.gateway import build_trace_metadata, complete_stream_async, complete_text
from finance_agent.llm.registry import get_profile_preset

# ── from_capability ──────────────────────────────


def test_from_capability_derives_max_context():
    cap = SimpleNamespace(max_context=200000)
    budget = ContextBudget.from_capability(cap)
    assert budget.max_context_tokens == 200000
    assert budget.system_reserve == 4000
    assert budget.output_reserve == 8000
    assert budget.tool_result_budget == 50000
    assert budget.compact_threshold_ratio == 0.85
    assert budget.usage_estimated is True


def test_from_capability_none_falls_back_to_default():
    budget = ContextBudget.from_capability(None)
    assert budget.max_context_tokens == 120000


# ── calibrate ────────────────────────────────────


def test_calibrate_none_marks_estimated():
    budget = ContextBudget()
    budget.calibrate(None)
    assert budget.usage_estimated is True


def test_calibrate_int_flips_and_raises_budget():
    budget = ContextBudget()  # max 120000
    budget.calibrate(150000)
    assert budget.usage_estimated is False
    # 150000 + 8192 > 120000 → 上抬至 int(150000 * 1.05) = 157500
    assert budget.max_context_tokens == 157500


def test_calibrate_small_usage_keeps_budget():
    budget = ContextBudget()
    budget.calibrate(1000)
    assert budget.usage_estimated is False
    assert budget.max_context_tokens == 120000


# ── build_trace_metadata 可选键 ──────────────────


def test_build_trace_metadata_optional_keys_present():
    profile = get_profile_preset("ark-glm")
    md = build_trace_metadata(
        profile, purpose="quick", max_tokens_source="requested", usage_estimated=True
    )
    assert md["max_tokens_source"] == "requested"
    assert md["usage_estimated"] is True


def test_build_trace_metadata_optional_keys_absent_by_default():
    profile = get_profile_preset("ark-glm")
    md = build_trace_metadata(profile, purpose="quick")
    assert "max_tokens_source" not in md
    assert "usage_estimated" not in md


# ── complete_text 返回 metadata 的 max_tokens_source ──


def _fake_completion_factory():
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="答"), finish_reason="stop")]
        )

    return fake_completion, captured


CFG = {"model": "glm-5.2", "baseUrl": "https://x/v1", "apiKey": "k"}


def test_complete_text_metadata_max_tokens_source_capability(monkeypatch):
    fake, _ = _fake_completion_factory()
    monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_completion", fake)
    _, md = complete_text([{"role": "user", "content": "hi"}], llm_config=CFG)
    assert md["max_tokens_source"] == "capability"


def test_complete_text_metadata_max_tokens_source_requested(monkeypatch):
    fake, _ = _fake_completion_factory()
    monkeypatch.setattr("finance_agent.llm.adapters.litellm_adapter.raw_completion", fake)
    _, md = complete_text([{"role": "user", "content": "hi"}], llm_config=CFG, max_tokens=1024)
    assert md["max_tokens_source"] == "requested"


# ── async 错误路径观测 error_type ────────────────


async def test_async_error_observation_includes_error_type(monkeypatch):
    class _Obs:
        def __init__(self):
            self.updated = {}

        def update(self, **kw):
            self.updated.update(kw)

    class _CM:
        def __enter__(self):
            return obs

        def __exit__(self, *a):
            return False

    obs = _Obs()
    monkeypatch.setattr(
        "finance_agent.langfuse_tracing.get_langfuse",
        lambda: type("_LF", (), {"start_as_current_observation": lambda self, **kw: _CM()})(),
    )

    async def fake_acompletion(**kwargs):  # noqa: ARG001
        raise litellm.exceptions.RateLimitError(message="limit", llm_provider="openai", model="m")

    import asyncio

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(
        "finance_agent.llm.adapters.litellm_adapter.raw_acompletion", fake_acompletion
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(LLMError):
        async for _ in complete_stream_async(
            [{"role": "user", "content": "hi"}],
            llm_config={
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://x/v1",
                "apiKey": "k",
            },
            trace={"name": "t"},
        ):
            pass
    assert obs.updated.get("metadata", {}).get("error_type")
