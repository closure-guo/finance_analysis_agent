"""BoundedEventSink 单测：有界入队分级处置 + 连续 undeliverable 熔断降级。

对应 delta spec: add-event-delivery-hardening（issue #227 第 2/6 项）。
覆盖：
- thinking 明细队列满即丢弃计数（既有语义保持）
- 边界事件与终态哨兵满队列时有界等待、空间释放后入队（spec「队列满时边界与
  终态事件不被丢弃」）
- 有界等待超时 → undeliverable 计数（既有语义保持）
- 连续 N 次 undeliverable → 非终态事件立即丢弃（breaker_degraded），哨兵豁免
- 成功入队重置连续计数（spec「成功入队重置熔断计数」）

断言全部基于 sink 返回的处置结果与注入的 record_drop 调用记录，
不依赖墙钟时序（防 CI flake）。
"""

from __future__ import annotations

import asyncio

import pytest

from finance_agent.agent_factory import BoundedEventSink


def _full_queue(maxsize: int = 2) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    for i in range(maxsize):
        q.put_nowait({"seed": i})
    return q


class _Drops:
    """record_drop 注入替身：记录 (session_id, kind) 调用序列。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, session_id: str, kind: str) -> None:
        self.calls.append((session_id, kind))


@pytest.mark.asyncio
async def test_thinking_dropped_when_queue_full():
    """droppable 明细：队列满即丢弃，计数 thinking 桶（既有语义）。"""
    q = _full_queue()
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=0.05)
    outcome = await sink.put({"type": "thinking_token"}, droppable=True)
    assert outcome == "dropped_thinking"
    assert drops.calls == [("s1", "thinking")]
    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_boundary_event_not_dropped_when_full_waits_for_space():
    """spec「队列满时边界与终态事件不被丢弃」：有界等待，空间释放后入队。"""
    q = _full_queue()
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=5.0)
    put_task = asyncio.create_task(sink.put({"type": "node_complete"}))
    await asyncio.sleep(0.05)  # put 已阻塞等待
    q.get_nowait()  # 消费者取走一条，空间释放
    outcome = await asyncio.wait_for(put_task, timeout=1.0)
    assert outcome == "enqueued"
    assert q.qsize() == 2
    assert drops.calls == []


@pytest.mark.asyncio
async def test_terminal_sentinel_waits_for_space():
    """流终结哨兵（None）与边界事件同权：满队列时有界等待而非丢弃。"""
    q = _full_queue()
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=5.0)
    put_task = asyncio.create_task(sink.put(None))
    await asyncio.sleep(0.05)
    q.get_nowait()
    outcome = await asyncio.wait_for(put_task, timeout=1.0)
    assert outcome == "enqueued"
    assert drops.calls == []


@pytest.mark.asyncio
async def test_bounded_wait_timeout_records_undeliverable():
    """有界等待超时：显式放弃并计 undeliverable 桶（既有语义）。"""
    q = _full_queue()
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=0.05)
    outcome = await sink.put({"type": "node_complete"})
    assert outcome == "undeliverable"
    assert drops.calls == [("s1", "undeliverable")]


@pytest.mark.asyncio
async def test_breaker_trips_after_consecutive_undeliverable():
    """spec「连续 undeliverable 触发熔断降级」：阈值后非终态事件立即丢弃计数。"""
    q = _full_queue()
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=0.05, breaker_threshold=3)
    for _ in range(3):
        assert await sink.put({"type": "node_complete"}) == "undeliverable"
    # 第 4 个非终态事件：熔断降级（若仍在有界等待，结果会是 undeliverable）
    outcome = await sink.put({"type": "tool_result"})
    assert outcome == "breaker_degraded"
    assert drops.calls[-1] == ("s1", "breaker_degraded")
    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_breaker_exempts_terminal_sentinel():
    """熔断后哨兵仍走有界等待路径——终态 MUST NOT 被熔断丢弃。"""
    q = _full_queue()
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=5.0, breaker_threshold=1)
    assert await sink.put({"type": "node_complete"}) == "undeliverable"  # 置位熔断
    sentinel_task = asyncio.create_task(sink.put(None))
    await asyncio.sleep(0.05)
    q.get_nowait()
    outcome = await asyncio.wait_for(sentinel_task, timeout=1.0)
    assert outcome == "enqueued"
    assert ("s1", "breaker_degraded") not in drops.calls


@pytest.mark.asyncio
async def test_successful_enqueue_resets_breaker_counter():
    """spec「成功入队重置熔断计数」：恢复后再单次失败不触发熔断。"""
    q = asyncio.Queue(maxsize=1)
    drops = _Drops()
    sink = BoundedEventSink(q, "s1", drops, timeout=0.05, breaker_threshold=2)
    q.put_nowait({"seed": 0})
    assert await sink.put({"type": "a"}) == "undeliverable"  # 连续 1
    q.get_nowait()
    assert await sink.put({"type": "b"}) == "enqueued"  # 成功 → 重置
    assert await sink.put({"type": "c"}) == "undeliverable"  # 重置后连续 1，不触发
    assert ("s1", "breaker_degraded") not in drops.calls
    assert drops.calls == [("s1", "undeliverable"), ("s1", "undeliverable")]
