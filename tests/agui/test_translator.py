"""translator TDD：harness StreamEvent → AG-UI 事件薄翻译层。

映射表以调研文档 docs/superpowers/research/2026-08-30-agui-assistant-ui-research.md
§2.2 十五行为权威源（用例覆盖 #1-#13）。
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from ag_ui.core.events import (
    EventType,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageStartEvent,
)

from finance_agent.agui.translator import translate_to_agui
from finance_agent.harness.types import StreamEvent, ToolCallRequest, ToolResult

THREAD_ID = "sess-1"
RUN_ID = "run-1"


def _events(*stream_events: StreamEvent) -> AsyncIterator[StreamEvent]:
    async def _gen() -> AsyncIterator[StreamEvent]:
        for ev in stream_events:
            yield ev

    return _gen()


async def _translate(*stream_events: StreamEvent) -> list[Any]:
    return [ev async for ev in translate_to_agui(_events(*stream_events), THREAD_ID, RUN_ID)]


def _types(events: list[Any]) -> list[EventType]:
    return [ev.type for ev in events]


# ── #1-#4：纯文本对话完整序列 ──


@pytest.mark.asyncio
async def test_pure_text_sequence() -> None:
    events = await _translate(StreamEvent.answer("你好"), StreamEvent.answer("，世界"))
    # #1 RUN_STARTED 为首个事件，thread/run id 直通
    first = events[0]
    assert isinstance(first, RunStartedEvent)
    assert first.type == EventType.RUN_STARTED
    assert first.thread_id == THREAD_ID
    assert first.run_id == RUN_ID
    # #2/#3/#4 TEXT_MESSAGE_START/CONTENT/END，message_id 全程一致
    assert _types(events[1:]) == [
        EventType.TEXT_MESSAGE_START,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_END,
        EventType.RUN_FINISHED,  # #13
    ]
    start = events[1]
    assert isinstance(start, TextMessageStartEvent)
    assert start.role == "assistant"
    assert all(ev.message_id == start.message_id for ev in events[1:5])
    assert events[2].delta == "你好"
    assert events[3].delta == "，世界"
    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.thread_id == THREAD_ID
    assert finished.run_id == RUN_ID


@pytest.mark.asyncio
async def test_empty_answer_delta_filtered() -> None:
    """风险 7：空 TEXT_MESSAGE_CONTENT delta 必须过滤（SDK 校验非空）。"""
    events = await _translate(
        StreamEvent.answer("he"),
        StreamEvent.answer(""),
        StreamEvent.answer("llo"),
    )
    contents = [ev for ev in events if ev.type == EventType.TEXT_MESSAGE_CONTENT]
    assert [ev.delta for ev in contents] == ["he", "llo"]
    # 空 delta 不得触发重复 START
    starts = [ev for ev in events if ev.type == EventType.TEXT_MESSAGE_START]
    assert len(starts) == 1


# ── #5-#8：思考段与 THINK_TO_ANSWER 换段 ──


@pytest.mark.asyncio
async def test_think_segment_lifecycle() -> None:
    events = await _translate(StreamEvent.think("想"), StreamEvent.think("1"))
    assert _types(events) == [
        EventType.RUN_STARTED,
        EventType.REASONING_MESSAGE_START,
        EventType.REASONING_MESSAGE_CONTENT,
        EventType.REASONING_MESSAGE_CONTENT,
        EventType.REASONING_MESSAGE_END,
        EventType.RUN_FINISHED,
    ]
    start = events[1]
    assert isinstance(start, ReasoningMessageStartEvent)
    assert start.role == "reasoning"
    assert all(ev.message_id == start.message_id for ev in events[1:5])


@pytest.mark.asyncio
async def test_think_to_answer_switches_segment() -> None:
    """#8：关闭当前 REASONING 段 + 打开 TEXT_MESSAGE_START（message_id 换段）。"""
    events = await _translate(
        StreamEvent.think("过程"),
        StreamEvent.think_to_answer("完整回答"),
    )
    assert _types(events) == [
        EventType.RUN_STARTED,
        EventType.REASONING_MESSAGE_START,
        EventType.REASONING_MESSAGE_CONTENT,
        EventType.REASONING_MESSAGE_END,
        EventType.TEXT_MESSAGE_START,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_END,
        EventType.RUN_FINISHED,
    ]
    reasoning = events[1]
    text = events[4]
    assert reasoning.message_id != text.message_id  # 换段：新 message_id
    assert events[5].delta == "完整回答"
    assert events[5].message_id == text.message_id


# ── #9：THINK_REPLACE 新段 ──


@pytest.mark.asyncio
async def test_think_replace_opens_new_segment() -> None:
    events = await _translate(
        StreamEvent.think("原始 <think>"),
        StreamEvent.think_replace("清理后"),
    )
    assert _types(events) == [
        EventType.RUN_STARTED,
        EventType.REASONING_MESSAGE_START,
        EventType.REASONING_MESSAGE_CONTENT,
        EventType.REASONING_MESSAGE_END,
        EventType.REASONING_MESSAGE_START,  # 新段（replace 语义）
        EventType.REASONING_MESSAGE_CONTENT,
        EventType.REASONING_MESSAGE_END,
        EventType.RUN_FINISHED,
    ]
    assert events[1].message_id != events[4].message_id
    assert events[5].delta == "清理后"
    assert events[5].message_id == events[4].message_id


# ── #10-#11：工具调用 id 一致 ──


@pytest.mark.asyncio
async def test_tool_call_result_id_consistency() -> None:
    call = ToolCallRequest(id="tc-1", name="web_search", arguments={"query": "贵州茅台"})
    result = ToolResult(tool_call_id="tc-1", name="web_search", output="搜索结果文本")
    events = await _translate(
        StreamEvent.for_tool_call(call),
        StreamEvent.for_tool_result(result),
    )
    assert _types(events) == [
        EventType.RUN_STARTED,
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_ARGS,  # ARGS 一次全量（#10）
        EventType.TOOL_CALL_RESULT,
        EventType.RUN_FINISHED,
    ]
    start = events[1]
    args = events[2]
    result_ev = events[3]
    # id 一致性：START/ARGS/RESULT 三者同一 tool_call_id
    assert start.tool_call_id == args.tool_call_id == result_ev.tool_call_id
    assert start.tool_call_name == "web_search"
    assert args.delta  # 非空 JSON 串
    assert '"query"' in args.delta
    assert result_ev.content == "搜索结果文本"


# ── #12：ERROR → RUN_ERROR ──


@pytest.mark.asyncio
async def test_error_maps_to_run_error_and_terminates() -> None:
    events = await _translate(StreamEvent.answer("部分"), StreamEvent.error("boom"))
    # RUN_ERROR 为终止事件：其后再无事件（不得输出半截 RUN_FINISHED）
    assert _types(events) == [
        EventType.RUN_STARTED,
        EventType.TEXT_MESSAGE_START,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_END,
        EventType.RUN_ERROR,
    ]
    err = events[-1]
    assert isinstance(err, RunErrorEvent)
    assert err.message == "boom"


# ── 无映射表行的事件不产出协议事件 ──


@pytest.mark.asyncio
async def test_unmapped_event_types_are_skipped() -> None:
    """PROGRESS/TOOL_METADATA 无映射表行：翻译层静默跳过，不影响段状态机。"""
    events = await _translate(
        StreamEvent.progress("进度"),
        StreamEvent.tool_metadata({"k": "v"}),
        StreamEvent.answer("答"),
    )
    assert _types(events) == [
        EventType.RUN_STARTED,
        EventType.TEXT_MESSAGE_START,
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TEXT_MESSAGE_END,
        EventType.RUN_FINISHED,
    ]
