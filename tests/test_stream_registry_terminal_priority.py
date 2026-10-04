"""publish_terminal 终态重试发布 + record_drop/backlog_stats 可观测单测。

对应 delta spec: add-event-delivery-resilience Task 2。
覆盖：
- publish_terminal：先落 journal 再 fan-out，返回分配的 seq
- publish_terminal：per-run CAS 去重（同轮重复终态返回 0）
- publish_terminal：journal 瞬断按 1s 间隔重试，恢复后成功
- publish_terminal：重试耗尽显式 raise（MUST NOT 静默吞掉终态缺失）
- record_drop / backlog_stats：明细丢弃计数与积压快照
"""

from __future__ import annotations

import asyncio

import pytest

from finance_agent import session_store, stream_registry
from finance_agent.stream_registry import SessionStream, StreamRegistry


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def _make_subscriber(reg: StreamRegistry, session_id: str) -> asyncio.Queue[dict | None]:
    """注册订阅者队列（直接操纵 _streams 的裸 stream，无 task——自足 helper）。"""
    stream = reg._streams.setdefault(session_id, SessionStream())  # noqa: SLF001
    q: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=stream_registry._SUBSCRIBER_QUEUE_MAX)  # noqa: SLF001
    stream.subscribers.append(q)
    return q


@pytest.mark.asyncio
async def test_publish_terminal_journals_and_fans_out(tmp_path, monkeypatch):
    """publish_terminal 先落 journal 再 fan-out，返回分配的 seq。"""
    _setup_db(tmp_path, monkeypatch)
    reg = StreamRegistry()
    sid = "s-term-1"
    q = _make_subscriber(reg, sid)
    seq = await reg.publish_terminal(sid, {"type": "done"})
    assert seq >= 1
    assert q.qsize() == 1
    assert q.get_nowait()["type"] == "done"
    rows = session_store.list_session_events(sid)
    assert rows[-1]["seq"] == seq


@pytest.mark.asyncio
async def test_publish_terminal_cas_dedup(tmp_path, monkeypatch):
    """同轮重复终态：第二条被 per-run CAS 拒绝（返回 0）。"""
    _setup_db(tmp_path, monkeypatch)
    reg = StreamRegistry()
    sid = "s-term-2"
    _make_subscriber(reg, sid)
    first = await reg.publish_terminal(sid, {"type": "done"})
    second = await reg.publish_terminal(sid, {"type": "done"})
    assert first >= 1 and second == 0


@pytest.mark.asyncio
async def test_publish_terminal_retries_then_succeeds(tmp_path, monkeypatch):
    """journal 瞬断：前 2 次失败后第 3 次成功，失败间隔按 1s 重试。"""
    _setup_db(tmp_path, monkeypatch)
    reg = StreamRegistry()
    sid = "s-term-3"
    _make_subscriber(reg, sid)
    calls = {"n": 0}
    real = session_store.append_session_event

    def flaky(sid_, ev):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("transient journal failure")
        return real(sid_, ev)

    monkeypatch.setattr(session_store, "append_session_event", flaky)
    sleeps: list[float] = []
    real_sleep = asyncio.sleep
    # registry 以 asyncio.sleep 引用重试间隔——patch 同一目标；捕获真身避免 lambda 自递归
    monkeypatch.setattr(asyncio, "sleep", lambda s: sleeps.append(s) or real_sleep(0))
    seq = await reg.publish_terminal(sid, {"type": "error", "message": "x"})
    assert seq >= 1 and calls["n"] == 3 and len(sleeps) == 2


@pytest.mark.asyncio
async def test_publish_terminal_exhaustion_raises(tmp_path, monkeypatch):
    """journal 持续不可用：5 次重试耗尽后显式 raise，不静默吞掉。"""
    _setup_db(tmp_path, monkeypatch)
    reg = StreamRegistry()
    sid = "s-term-4"
    _make_subscriber(reg, sid)

    def journal_down(*args, **kwargs):
        raise RuntimeError("journal down")

    monkeypatch.setattr(session_store, "append_session_event", journal_down)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda s: real_sleep(0))
    with pytest.raises(RuntimeError):
        await reg.publish_terminal(sid, {"type": "done"})


def test_record_drop_and_backlog_stats():
    """record_drop 按 kind 计数；backlog_stats 无 stream 时 subscribers=0、last_seq=0。"""
    reg = StreamRegistry()
    sid = "s-drop-1"
    reg.record_drop(sid, "thinking")
    reg.record_drop(sid, "thinking")
    reg.record_drop(sid, "chunk")
    stats = reg.backlog_stats(sid)
    assert stats["drops"] == {"thinking": 2, "chunk": 1}
    assert stats["subscribers"] == 0
    assert stats["last_seq"] == 0
