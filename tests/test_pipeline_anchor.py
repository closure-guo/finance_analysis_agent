"""pipeline_anchor 锚点持久化测试。

对应 change: fix-history-report-anchor Task 1。
验证：
- set_pipeline_anchor 将锚点写为最后一条 role='user' 条目索引 + 1
- init_db 幂等迁移添加 pipeline_anchor 列，既有行保持 NULL
- fast path 管线启动后 session 的 pipeline_anchor = 1
- GET /api/sessions/{id} 响应包含 pipeline_anchor 字段
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

import finance_agent.api as api_mod
from finance_agent import session_store
from finance_agent.api import app
from finance_agent.pipeline_runner import PipelineRunner


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """隔离的 session DB（指向 tmp_path，避免测试污染开发库）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


# ── Task 1.1: set_pipeline_anchor 锚点计算 ──


def test_set_pipeline_anchor_multi_turn(tmp_path, monkeypatch):
    """多轮澄清 [user1, assistant1, user2] → 锚点 = 3（最后一条 user 索引 + 1）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="", stock_name="", status="clarifying")
    session_store.append_chat(sid, "user", "分析一下热门股票")
    session_store.append_chat(sid, "assistant", "我来搜索最新热点")
    session_store.append_chat(sid, "user", "中际旭创")

    session_store.set_pipeline_anchor(sid)

    row = session_store.get_session(sid)
    assert row["pipeline_anchor"] == 3


def test_set_pipeline_anchor_single_user(tmp_path, monkeypatch):
    """单轮 fast path [user1] → 锚点 = 1。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="", stock_name="", status="clarifying")
    session_store.append_chat(sid, "user", "分析贵州茅台")

    session_store.set_pipeline_anchor(sid)

    row = session_store.get_session(sid)
    assert row["pipeline_anchor"] == 1


def test_set_pipeline_anchor_no_user(tmp_path, monkeypatch):
    """chat_history 无 user 消息时不写锚点（保持 NULL）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="", stock_name="", status="clarifying")
    session_store.append_chat(sid, "assistant", "你好")

    session_store.set_pipeline_anchor(sid)

    row = session_store.get_session(sid)
    assert row["pipeline_anchor"] is None


def test_set_pipeline_anchor_ignores_inflight_assistant(tmp_path, monkeypatch):
    """ReAct 路径 assistant 在途 upsert 不影响锚点：[user1, assistant1, user2, assistant2(在途)] → 仍为 3。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="", stock_name="", status="clarifying")
    session_store.append_chat(sid, "user", "分析一下热门股票")
    session_store.append_chat(sid, "assistant", "我来搜索")
    session_store.append_chat(sid, "user", "中际旭创")
    # 模拟 10s 增量 upsert 的在途 assistant 消息
    session_store.upsert_chat(sid, "assistant", "正在分析...")

    session_store.set_pipeline_anchor(sid)

    row = session_store.get_session(sid)
    assert row["pipeline_anchor"] == 3


# ── Task 1.2: init_db 幂等迁移 ──


def test_pipeline_anchor_column_migration(tmp_path, monkeypatch):
    """init_db 幂等迁移添加 pipeline_anchor 列，既有行保持 NULL。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="completed")
    row = session_store.get_session(sid)
    # 新建会话未写锚点时应为 NULL
    assert row["pipeline_anchor"] is None
    # 重复 init_db 不报错（幂等）
    session_store.init_db()
    row2 = session_store.get_session(sid)
    assert row2["pipeline_anchor"] is None


# ── Task 1.3: fast path 管线启动后锚点 = 1 ──


def test_fast_path_sets_pipeline_anchor(isolated_db, monkeypatch):
    """fast path（stock_code 且无 session_id）管线启动后 pipeline_anchor = 1。"""

    def fake_stream(*args, **kwargs):
        yield _sse({"type": "analysis_start", "session_id": "x"})
        yield _sse({"type": "report_ready", "report_markdown": "# ok"})

    monkeypatch.setattr(api_mod, "_run_graph_streaming", fake_stream)

    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/api/analyze",
            json={
                "query": "分析贵州茅台",
                "stock_code": "600519",
                "stock_name": "贵州茅台",
            },
        ) as resp,
    ):
        sid = None
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("session_id"):
                    sid = ev["session_id"]
                    break

    assert sid is not None
    # 等后台推进完成
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    row = session_store.get_session(sid)
    assert row["pipeline_anchor"] == 1


# ── Task 1.4: GET /api/sessions/{id} 响应包含 pipeline_anchor ──


def test_session_detail_includes_pipeline_anchor(isolated_db):
    """GET /api/sessions/{id} 响应包含 pipeline_anchor 字段。"""
    with TestClient(app) as client:
        sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
        session_store.append_chat(sid, "user", "分析茅台")
        session_store.set_pipeline_anchor(sid)

        resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_anchor" in data
    assert data["pipeline_anchor"] == 1


def test_session_detail_pipeline_anchor_null_for_old_sessions(isolated_db):
    """未写入锚点的旧会话，pipeline_anchor 为 None。"""
    with TestClient(app) as client:
        sid = session_store.create_session(
            stock_code="600519", stock_name="茅台", status="completed"
        )

        resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("pipeline_anchor") is None
