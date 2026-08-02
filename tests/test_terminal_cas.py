"""终态 CAS 检查 + cancel 幂等测试。"""

from __future__ import annotations

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
    """先 publish done，再 publish interrupted，第二条应被拒绝（返回 0）。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    seq1 = await reg.publish(sid, {"type": "done"})
    assert seq1 > 0

    seq2 = await reg.publish(sid, {"type": "interrupted"})
    assert seq2 == 0  # CAS 拒绝

    # journal 中只有一条终态事件
    events = session_store.list_session_events(sid)
    terminal_events = [
        e
        for e in events
        if json.loads(e["event_json"]).get("type") in ("done", "interrupted", "error")
    ]
    assert len(terminal_events) == 1


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
