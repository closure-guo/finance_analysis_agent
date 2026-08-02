"""StreamRegistry 单测：任务与订阅管理。

对应 delta spec: resume-stream-on-session-switch Task 2.6。
覆盖：
- single-flight：已有活跃任务时 start 返回 False
- publish：先落库再 fan-out
- subscribe：先重放 journal 再接续实时
- cancel：task.cancel() 后注销
- 断开不杀任务
- 任务完成自动注销
"""

from __future__ import annotations

import asyncio

import pytest

from finance_agent import session_store, stream_registry


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


async def _next_event(gen, timeout=2.0):
    """从 AsyncGenerator 取下一个事件，超时失败。"""
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


@pytest.mark.asyncio
async def test_single_flight_rejects_duplicate(tmp_path, monkeypatch):
    """同一会话已有活跃任务时，start 返回 False。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def dummy_task():
        await asyncio.sleep(10)

    assert await reg.start(sid, dummy_task()) is True
    assert await reg.start(sid, dummy_task()) is False
    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_publish_persists_and_fans_out(tmp_path, monkeypatch):
    """publish 先落库再 fan-out 给订阅者。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def dummy_task():
        await asyncio.sleep(10)

    await reg.start(sid, dummy_task())

    # 注册订阅者
    gen = reg.subscribe(sid, after_seq=0)

    # 发布事件
    await reg.publish(sid, {"type": "thinking_token", "token": "hello"})

    # 订阅者应收到事件
    event = await _next_event(gen)
    assert event["type"] == "thinking_token"

    # 事件应已落库
    events = session_store.list_session_events(sid, after_seq=0)
    assert len(events) >= 1
    assert reg.is_active(sid)
    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_subscribe_replays_journal(tmp_path, monkeypatch):
    """subscribe 先重放历史事件再接续实时。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def dummy_task():
        await asyncio.sleep(10)

    await reg.start(sid, dummy_task())

    # 先发布两个事件（无订阅者，仅落库）
    await reg.publish(sid, {"type": "token", "idx": 1})
    await reg.publish(sid, {"type": "token", "idx": 2})

    # 订阅者从 seq=0 开始，应重放历史 + 接续实时
    gen = reg.subscribe(sid, after_seq=0)

    # 收到重放的事件 1
    e1 = await _next_event(gen)
    assert e1["idx"] == 1
    # 收到重放的事件 2
    e2 = await _next_event(gen)
    assert e2["idx"] == 2

    # 发布新事件，订阅者应实时收到
    await reg.publish(sid, {"type": "token", "idx": 3})
    e3 = await _next_event(gen)
    assert e3["idx"] == 3

    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_cancel_task(tmp_path, monkeypatch):
    """cancel 后任务被取消且从 registry 注销。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    cancelled = asyncio.Event()

    async def dummy_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            print("[TEST] CancelledError caught in dummy_task")
            cancelled.set()
            raise

    assert await reg.start(sid, dummy_task()) is True
    # 让事件循环有机会调度 _run_task
    await asyncio.sleep(0.05)
    assert reg.is_active(sid)
    print("[TEST] task is active, cancelling...")

    result = await reg.cancel(sid)
    print(f"[TEST] cancel returned: {result}")
    assert result is True

    # 等待 CancelledError 被捕获
    await asyncio.wait_for(cancelled.wait(), timeout=5.0)
    print("[TEST] cancelled event set")
    assert not reg.is_active(sid)


@pytest.mark.asyncio
async def test_task_cleanup_on_complete(tmp_path, monkeypatch):
    """任务正常完成后自动从 registry 注销。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def quick_task():
        await asyncio.sleep(0.1)

    assert await reg.start(sid, quick_task()) is True
    assert reg.is_active(sid)

    # 等待任务完成
    await asyncio.sleep(0.5)
    assert not reg.is_active(sid)


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false(tmp_path, monkeypatch):
    """cancel 无活跃任务的会话返回 False。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="completed")

    assert await reg.cancel(sid) is False


@pytest.mark.asyncio
async def test_subscribe_no_active_task_sends_terminal(tmp_path, monkeypatch):
    """无活跃任务时 subscribe 重放后下发终态事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="interrupted")

    # 手动写入一些历史事件
    session_store.append_session_event(sid, {"type": "token", "idx": 1})

    # 订阅（无活跃任务）
    gen = reg.subscribe(sid, after_seq=0)

    # 应收到重放的历史事件
    e1 = await _next_event(gen)
    assert e1["idx"] == 1

    # 应收到终态事件（interrupted 或 done）
    terminal = await _next_event(gen)
    assert terminal["type"] in ("interrupted", "done")
