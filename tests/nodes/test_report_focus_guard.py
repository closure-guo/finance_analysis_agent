# tests/nodes/test_report_focus_guard.py
"""_build_focus_summary 输出合同集成（delta add-output-contract-guard）。"""

from __future__ import annotations

from unittest.mock import patch

from finance_agent.nodes import report as report_mod
from finance_agent.nodes.report import _build_focus_summary

_LEAKED = (
    "The user wants a 150-200 character research focus summary.\n\n"
    "Key points to weave in:\n\nDraft:\n\n“综合裁决为中性……PE_ttm 85."
)
_CLEAN = "拓荆科技多空证据均衡，给予中性评级（置信度0.50），维持观望，等待扣非口径验证后择向。"

_STATE = {
    "api_key": None,
    "stock_name": "拓荆科技",
    "analyst_reports": {"fundamental": {"summary": "基本面摘要"}},
    "research_manager_conclusion": "研究结论：中性",
    "final_trade_decision": {"action": "watch", "reasoning": "观望"},
    "llm_config": None,
}


def test_clean_first_call_passes_through():
    calls = []

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        calls.append(messages)
        return _CLEAN, {"finish_reason": "stop"}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert out == _CLEAN
    assert len(calls) == 1


def test_leak_triggers_retry_with_strengthened_instruction():
    calls = []

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        calls.append(messages)
        if len(calls) == 1:
            return _LEAKED, {"finish_reason": "stop"}
        return _CLEAN, {"finish_reason": "stop"}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert out == _CLEAN
    assert len(calls) == 2
    assert "禁止" in calls[1][0]["content"]  # 强化指令落在第二次的 system


def test_double_leak_falls_back_to_structured_join():
    calls = []

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        calls.append(messages)
        return _LEAKED, {"finish_reason": "stop"}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert out == "[fundamental] 基本面摘要"[:200]
    assert len(calls) == 2


def test_empty_content_with_reasoning_not_delivered():
    """raw_reasoning 回退坑关闭：content 空时不得把 reasoning 当交付文本。"""
    reasoning_text = "Let me think about the summary. I will write it now."

    def fake_complete_text(messages, **kwargs):  # noqa: ARG002
        return "", {"finish_reason": "stop", "raw_reasoning": reasoning_text}

    with patch.object(report_mod, "complete_text", side_effect=fake_complete_text):
        out = _build_focus_summary(_STATE, "", ["综合"])
    assert reasoning_text not in out
    assert out == "[fundamental] 基本面摘要"[:200]
