"""harness StreamEvent → AG-UI 事件薄翻译层。

映射表（权威源）：docs/superpowers/research/2026-08-30-agui-assistant-ui-research.md
§2.2 十五行。协议类型与编码由官方 SDK（ag-ui-protocol）承担，本模块仅做事件翻译。

设计要点：
- 纯函数级可测，不依赖 FastAPI / registry；
- 状态机维护当前 reasoning / text 段开闭：段内事件（THINK/ANSWER delta、工具事件）
  不重复开段，跨段事件（THINK_TO_ANSWER / THINK_REPLACE / 换类型 / 终态）正确闭段；
- 空 TEXT/REASONING delta 一律过滤（调研文档风险 7，SDK 校验 delta 非空）；
- ERROR → RUN_ERROR 且终止翻译（RUN_ERROR 是唯一终止事件，不再补发 RUN_FINISHED）；
- PROGRESS / TOOL_METADATA 无映射表行，静默跳过；
- 工具调用分配 AG-UI tool_call_id 并保证 TOOL_CALL_START / ARGS / RESULT 一致。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from ag_ui.core.events import (
    BaseEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

from finance_agent.harness.types import ActionType, StreamEvent


class _SegmentState:
    """当前开着的 AG-UI 消息段。段类型二选一，开段时分配 message_id。"""

    __slots__ = ("kind", "message_id")

    def __init__(self) -> None:
        self.kind: str | None = None  # "reasoning" | "text" | None
        self.message_id: str = ""

    def open_reasoning(self) -> str:
        self.message_id = uuid.uuid4().hex
        self.kind = "reasoning"
        return self.message_id

    def open_text(self) -> str:
        self.message_id = uuid.uuid4().hex
        self.kind = "text"
        return self.message_id

    def reset(self) -> None:
        self.kind = None
        self.message_id = ""

    @property
    def is_reasoning(self) -> bool:
        return self.kind == "reasoning"

    @property
    def is_text(self) -> bool:
        return self.kind == "text"


def _close_event(seg: _SegmentState) -> BaseEvent | None:
    """闭当前段产生的 END 事件（无开段时 None）。"""
    if seg.kind == "reasoning":
        return ReasoningMessageEndEvent(message_id=seg.message_id)
    if seg.kind == "text":
        return TextMessageEndEvent(message_id=seg.message_id)
    return None


async def translate_to_agui(
    events: AsyncIterator[StreamEvent],
    thread_id: str,
    run_id: str,
) -> AsyncIterator[BaseEvent]:
    """将 harness Agent 的 StreamEvent 流翻译为 AG-UI 官方事件流。

    Args:
        events: agent.run() 产出的 StreamEvent 异步流
        thread_id: AG-UI thread_id（= session_id）
        run_id: AG-UI run_id

    Yields:
        ag_ui.core.events 官方事件对象（经 EventEncoder 编码后为 SSE）
    """
    seg = _SegmentState()
    # harness tool_call id -> 本层分配的 AG-UI tool_call_id（TOOL_RESULT 回查保证一致）
    tool_ids: dict[str, str] = {}
    yield RunStartedEvent(thread_id=thread_id, run_id=run_id)  # 映射表 #1

    async for event in events:
        et = event.event_type

        if et == ActionType.ANSWER:  # #2/#3
            if not event.content:
                continue  # 空 delta 过滤（风险 7）
            if not seg.is_text:
                closed = _close_event(seg)
                if closed is not None:
                    yield closed
                mid = seg.open_text()
                yield TextMessageStartEvent(message_id=mid, role="assistant")
            yield TextMessageContentEvent(message_id=seg.message_id, delta=event.content)

        elif et == ActionType.THINK:  # #5/#6
            if not event.content:
                continue
            if not seg.is_reasoning:
                closed = _close_event(seg)
                if closed is not None:
                    yield closed
                mid = seg.open_reasoning()
                yield ReasoningMessageStartEvent(message_id=mid, role="reasoning")
            yield ReasoningMessageContentEvent(message_id=seg.message_id, delta=event.content)

        elif et == ActionType.THINK_TO_ANSWER:  # #8
            # 关闭当前 REASONING 段 + 打开 TEXT 段（message_id 换段）；content 为
            # 完整回答文本，以单个 TEXT_MESSAGE_CONTENT 全量下发，换段后回答不丢失。
            closed = _close_event(seg)
            if closed is not None:
                yield closed
            mid = seg.open_text()
            yield TextMessageStartEvent(message_id=mid, role="assistant")
            if event.content:
                yield TextMessageContentEvent(message_id=mid, delta=event.content)

        elif et == ActionType.THINK_REPLACE:  # #9
            # replace 语义：闭当前段，开新 REASONING 段（新 message_id）并全量下发。
            closed = _close_event(seg)
            if closed is not None:
                yield closed
            mid = seg.open_reasoning()
            yield ReasoningMessageStartEvent(message_id=mid, role="reasoning")
            if event.content:
                yield ReasoningMessageContentEvent(message_id=mid, delta=event.content)

        elif et == ActionType.TOOL_CALL:  # #10
            tc = event.tool_call
            if tc is None:
                continue  # permission_required 形态：无映射表行，跳过
            closed = _close_event(seg)
            if closed is not None:
                yield closed
            agui_id = uuid.uuid4().hex
            if tc.id:
                tool_ids[tc.id] = agui_id
            yield ToolCallStartEvent(tool_call_id=agui_id, tool_call_name=tc.name)
            # ARGS 一次全量（#10）
            yield ToolCallArgsEvent(
                tool_call_id=agui_id, delta=json.dumps(tc.arguments, ensure_ascii=False)
            )

        elif et == ActionType.TOOL_RESULT:  # #11
            tr = event.tool_result
            if tr is None:
                continue
            # 回查 TOOL_CALL 分配的 AG-UI id，保证 START/ARGS/RESULT 一致
            agui_id = tool_ids.get(tr.tool_call_id, tr.tool_call_id)
            yield ToolCallResultEvent(
                message_id=uuid.uuid4().hex,
                tool_call_id=agui_id,
                content=tr.output,
            )

        elif et == ActionType.ERROR:  # #12
            closed = _close_event(seg)
            if closed is not None:
                yield closed
            yield RunErrorEvent(message=event.content)
            return  # RUN_ERROR 为唯一终止事件，不再补发 RUN_FINISHED

        # PROGRESS / TOOL_METADATA / 其它：无映射表行，静默跳过

    # 事件流耗尽：闭段 + RUN_FINISHED（#4/#7/#13）
    closed = _close_event(seg)
    if closed is not None:
        yield closed
    yield RunFinishedEvent(thread_id=thread_id, run_id=run_id)
