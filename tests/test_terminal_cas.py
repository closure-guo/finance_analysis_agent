"""终态 CAS 检查 + cancel 幂等测试。"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store, stream_registry


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


@pytest.mark.asyncio
async def test_publish_cas_rejects_second_terminal(tmp_path, monkeypatch):
    """同一轮运行内：先 publish done，再 publish interrupted，第二条应被拒绝（返回 0）。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def long_task():
        await asyncio.sleep(1.0)

    await reg.start(sid, long_task())
    await asyncio.sleep(0.05)  # 让 _run_task 启动

    seq1 = await reg.publish(sid, {"type": "done"})
    assert seq1 > 0

    seq2 = await reg.publish(sid, {"type": "interrupted"})
    assert seq2 == 0  # 同轮 CAS 拒绝

    # journal 中只有一条终态事件
    events = session_store.list_session_events(sid)
    terminal_events = [
        e
        for e in events
        if json.loads(e["event_json"]).get("type") in ("done", "interrupted", "error")
    ]
    assert len(terminal_events) == 1

    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_publish_cas_allows_non_terminal_after_terminal(tmp_path, monkeypatch):
    """终态后非终态事件不受 CAS 限制。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    await reg.publish(sid, {"type": "done"})
    seq = await reg.publish(sid, {"type": "thinking_token", "token": "late"})
    assert seq > 0


def test_cancel_idempotent_returns_terminal(tmp_path, monkeypatch):
    """cancel 无活跃任务但有终态事件时返回终态而非 404。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="interrupted")
    session_store.append_session_event(sid, {"type": "interrupted"})

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.post(f"/api/sessions/{sid}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "interrupted"


def test_cancel_no_task_no_terminal_returns_404(tmp_path, monkeypatch):
    """cancel 无活跃任务且无终态事件时返回 404。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.post(f"/api/sessions/{sid}/cancel")
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_type", ["done", "interrupted", "error"])
async def test_per_run_cas_allows_terminal_in_second_round(terminal_type, tmp_path, monkeypatch):
    """同一会话两轮终态事件，第二轮不被吞（per-run CAS 不跨轮）。

    覆盖 done/interrupted/error 三种终态类型。
    """
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    # 第一轮：start + publish done
    async def round1_task():
        await asyncio.sleep(0.3)

    await reg.start(sid, round1_task())
    await asyncio.sleep(0.05)  # 让 _run_task 启动
    seq1 = await reg.publish(sid, {"type": "done"})
    assert seq1 > 0

    # 等待第一轮任务完成并注销
    await asyncio.sleep(0.5)
    assert not reg.is_active(sid)

    # 第二轮：start + publish terminal_type（不应被吞）
    async def round2_task():
        await asyncio.sleep(0.3)

    await reg.start(sid, round2_task())
    await asyncio.sleep(0.05)
    event = {"type": terminal_type}
    if terminal_type == "error":
        event["message"] = "test error"
    seq2 = await reg.publish(sid, event)
    assert seq2 > 0, f"第二轮 {terminal_type} 事件被吞（per-run CAS 误跨轮）"

    # 等待第二轮任务完成（_run_task 的自动 done 被 CAS 拒绝）
    await asyncio.sleep(0.5)
    assert not reg.is_active(sid)

    # 验证 journal 中有两轮终态事件
    events = session_store.list_session_events(sid)
    terminal_events = [
        e
        for e in events
        if json.loads(e["event_json"]).get("type") in ("done", "interrupted", "error")
    ]
    assert len(terminal_events) == 2


@pytest.mark.asyncio
async def test_per_run_cas_rejects_duplicate_done_within_same_run(tmp_path, monkeypatch):
    """同一轮运行内重复 done 事件被去重（第二个返回 0）。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def long_task():
        await asyncio.sleep(1.0)

    await reg.start(sid, long_task())
    await asyncio.sleep(0.05)

    seq1 = await reg.publish(sid, {"type": "done"})
    assert seq1 > 0

    seq2 = await reg.publish(sid, {"type": "done"})
    assert seq2 == 0  # 同轮内去重

    await reg.cancel(sid)
