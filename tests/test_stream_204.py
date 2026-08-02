"""stream_session 204 语义测试。"""

from fastapi.testclient import TestClient

from finance_agent import session_store


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def test_stream_returns_204_when_no_events_no_active(tmp_path, monkeypatch):
    """无事件且无活跃任务时返回 204。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.get(f"/api/sessions/{sid}/stream")
    assert resp.status_code == 204


def test_stream_returns_200_when_events_exist(tmp_path, monkeypatch):
    """有事件时返回 200 SSE 流。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")
    session_store.append_session_event(sid, {"type": "done"})

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.get(f"/api/sessions/{sid}/stream")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_stream_returns_404_when_session_not_found(tmp_path, monkeypatch):
    """session 不存在时返回 404。"""
    _setup_db(tmp_path, monkeypatch)

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.get("/api/sessions/nonexistent/stream")
    assert resp.status_code == 404
