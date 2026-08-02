"""第 6 组：API 层返回 failure_reason 字段测试。

验证：
- GET /api/sessions/{id} 对 failed 会话返回 failure_reason 字段
- GET /api/sessions 列表接口对 failed 会话返回 failure_reason 字段
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """隔离的 session DB（指向 tmp_path，避免测试污染开发库）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


def test_session_detail_returns_failure_reason(isolated_db):
    """GET /api/sessions/{id} 对 failed 会话 SHALL 返回 failure_reason 字段。

    注意：startup 钩子会清扫 running 会话，因此需先进入 TestClient 再建会话。
    """
    with TestClient(app) as client:
        # 创建 running 会话后标记为 failed 并写入 failure_reason
        sid = session_store.create_session(
            stock_code="600519", stock_name="贵州茅台", status="running"
        )
        session_store.update_session_status(sid, "failed", failure_reason="管线执行超时")

        resp = client.get(f"/api/sessions/{sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["failure_reason"] == "管线执行超时"


def test_session_detail_failure_reason_none_when_not_set(isolated_db):
    """未设置 failure_reason 的会话，详情接口返回 None。"""
    with TestClient(app) as client:
        sid = session_store.create_session(
            stock_code="600519", stock_name="贵州茅台", status="completed"
        )

        resp = client.get(f"/api/sessions/{sid}")

    assert resp.status_code == 200
    data = resp.json()
    assert "failure_reason" in data
    assert data["failure_reason"] is None


def test_session_list_returns_failure_reason(isolated_db):
    """GET /api/sessions 列表接口对 failed 会话返回 failure_reason 字段。"""
    with TestClient(app) as client:
        sid = session_store.create_session(
            stock_code="600519", stock_name="贵州茅台", status="running"
        )
        session_store.update_session_status(sid, "failed", failure_reason="数据获取失败")

        resp = client.get("/api/sessions")

    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    # 找到刚创建的 failed 会话
    target = [s for s in sessions if s["session_id"] == sid]
    assert len(target) == 1
    assert target[0]["status"] == "failed"
    assert target[0]["failure_reason"] == "数据获取失败"
