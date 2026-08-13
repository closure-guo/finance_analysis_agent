"""subscribe 先注册队列再读日志测试：重放期间有新事件产生时不丢事件。"""

# ruff: noqa: N802, S105
# N802: 用户规则要求 camelCase（dummyTask 与现有测试一致）
# S105: ruff 误报——"token" 是 SSE 事件字段名，非密码

from __future__ import annotations

import asyncio

import pytest

from finance_agent import session_store, stream_registry


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


@pytest.mark.asyncio
async def test_subscribe_no_event_loss_during_replay(tmp_path, monkeypatch):
    """重放期间有新事件产生时，先注册队列再读日志不丢事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    # 预置 2 条历史事件
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "b"})

    async def dummyTask():
        await asyncio.sleep(10)

    await reg.start(sid, dummyTask())

    # 启动订阅（在另一个 task 中）
    gen = reg.subscribe(sid, after_seq=0)

    # 取第一个事件（重放的历史事件）
    event1 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event1["type"] == "thinking_token"

    # 在重放期间发布新事件（模拟重放期间有新事件产生）
    await reg.publish(sid, {"type": "thinking_token", "token": "c"})

    # 继续消费：应收到第二条历史事件和新事件
    event2 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event2["type"] == "thinking_token"

    event3 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event3["type"] == "thinking_token"
    # 新事件不丢失
    tokens = [event1.get("token"), event2.get("token"), event3.get("token")]
    assert "c" in tokens

    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_subscribe_replays_then_realtime(tmp_path, monkeypatch):
    """subscribe 先重放历史事件，再接续实时事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    # 预置 1 条历史事件
    session_store.append_session_event(sid, {"type": "chat_token", "token": "old"})

    async def dummyTask():
        await asyncio.sleep(10)

    await reg.start(sid, dummyTask())

    gen = reg.subscribe(sid, after_seq=0)

    # 重放历史事件
    event1 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event1["token"] == "old"

    # 发布实时事件
    await reg.publish(sid, {"type": "chat_token", "token": "new"})

    # 消费实时事件
    event2 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event2["token"] == "new"

    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_subscribe_terminal_when_no_active(tmp_path, monkeypatch):
    """无活跃任务时，重放后下发终态事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="completed")

    # 预置 1 条历史事件 + 1 条终态事件
    session_store.append_session_event(sid, {"type": "chat_token", "token": "hello"})
    session_store.append_session_event(sid, {"type": "done"})

    gen = reg.subscribe(sid, after_seq=0)

    # 重放历史事件
    event1 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event1["token"] == "hello"

    # 终态事件
    event2 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event2["type"] == "done"

    # 重放不再因历史终态截断（多轮会话修复）：journal 真实 done 之后，
    # 无活跃任务会再补一个合成 done，随后流结束
    remaining = []
    with pytest.raises(StopAsyncIteration):
        while True:
            remaining.append(await asyncio.wait_for(gen.__anext__(), timeout=2.0))
    assert all(e["type"] in ("done", "interrupted", "error") for e in remaining)
