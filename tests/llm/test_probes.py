# tests/llm/test_probes.py
"""capability probe 纯函数层测试（delta 4.1）。

五项探测（non_stream/stream/tool_call/tool_followup/json_output）的
判定逻辑为纯函数——探测调用的发送编排在 api 层，判定在此可测。
"""

from __future__ import annotations

import pytest

from finance_agent.llm.probes import (
    ProbeReport,
    judge_capability_from_probe,
)


def _all_pass() -> ProbeReport:
    return ProbeReport(
        non_stream=True,
        stream=True,
        tool_call=True,
        tool_followup=True,
        json_output=True,
        latency_ms=120,
        warnings=[],
    )


def _chat_only() -> ProbeReport:
    return ProbeReport(
        non_stream=True,
        stream=True,
        tool_call=False,
        tool_followup=False,
        json_output=True,
        latency_ms=90,
        warnings=[
            "tool_choice_required_unsupported",
        ],
    )


class TestBuildProbeReport:
    def test_all_pass(self):
        r = _all_pass()
        assert all([r.non_stream, r.stream, r.tool_call, r.tool_followup, r.json_output])
        assert r.latency_ms == 120

    def test_chat_only_chat_but_no_tools(self):
        r = _chat_only()
        assert r.tool_call is False
        assert r.tool_followup is False

    def test_warnings(self):
        assert "tool_choice_required_unsupported" in _chat_only().warnings


class TestJudgeCapability:
    def test_full_profile(self):
        judges = judge_capability_from_probe(_all_pass())
        assert judges.tools == "single"
        assert judges.streaming is True

    def test_chat_only_profile_no_tools(self):
        judges = judge_capability_from_probe(_chat_only())
        assert judges.tools == "none"
        assert judges.json_schema == "json_mode"  # json_output 通过

    def test_probe_facts_override_static(self):
        """design 决策 7：probe 运行时事实覆盖静态能力表。"""
        from finance_agent.llm.probes import merge_probe_into_profile
        from finance_agent.llm.registry import get_profile_preset

        profile = get_profile_preset("anthropic")  # 静态声称 native tools
        merged = merge_probe_into_profile(profile, _chat_only())
        assert merged.capability.tools == "none"  # probe 事实优先


@pytest.mark.parametrize(
    ("latency", "expected"),
    [(60, "fast"), (800, "medium"), (3000, "slow")],
)
def test_latency_tier(latency, expected):
    from finance_agent.llm.probes import _latency_tier

    assert _latency_tier(latency) == expected


class TestRunLiveProbes:
    """五项探测执行（mock litellm）：判定编排可测。"""

    def test_all_capabilities_pass(self, monkeypatch):
        import litellm

        from finance_agent.llm.probes import run_live_probes

        calls = {"n": 0}

        def fake_completion(**kwargs):
            calls["n"] += 1
            from types import SimpleNamespace

            msgs = kwargs.get("messages") or []
            is_followup = any(m.get("role") == "tool" for m in msgs)
            msg = SimpleNamespace(
                content='{"ok": true}' if kwargs.get("response_format") else "好的",
                tool_calls=(
                    None
                    if is_followup
                    else [
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(name="probe_echo", arguments='{"text":"x"}'),
                        )
                    ]
                    if kwargs.get("tools")
                    else None
                ),
            )
            choice = SimpleNamespace(message=msg, finish_reason="stop")
            return SimpleNamespace(choices=[choice])

        monkeypatch.setattr(litellm, "completion", fake_completion)
        report = run_live_probes(
            model="openai/glm-5.2",
            api_key="k",
            base_url="https://x/v1",
        )
        assert report.non_stream is True
        assert report.tool_call is True
        assert report.tool_followup is True
        assert report.json_output is True

    def test_tool_probe_failure_marks_none(self, monkeypatch):
        import litellm

        from finance_agent.llm.probes import run_live_probes

        def fake_completion(**kwargs):
            from types import SimpleNamespace

            msg = SimpleNamespace(content="好的", tool_calls=None)
            choice = SimpleNamespace(message=msg, finish_reason="stop")
            return SimpleNamespace(choices=[choice])

        monkeypatch.setattr(litellm, "completion", fake_completion)
        report = run_live_probes(model="x", api_key="k", base_url="https://x")
        assert report.tool_call is False
        assert report.tool_followup is False
