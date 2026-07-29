"""Task 3: /api/analyze fast path 管线后台化接线测试。

红线验证：SSE 断开后后台管线继续推进快照（PipelineRunner + 事件队列）。
"""

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


def test_session_detail_includes_pipeline_snapshot(isolated_db):
    """GET /api/sessions/{id} 返回体自动带出 pipeline_snapshot 字段。

    注意：startup 钩子会清扫 running 会话，因此需先进入 TestClient 再建会话。
    """
    with TestClient(app) as client:
        sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
        session_store.update_pipeline_snapshot(
            sid,
            {"layerTree": [], "currentNodeId": "x", "progress": 0.1, "updatedAt": 1},
        )

        resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_snapshot" in data
    assert json.loads(data["pipeline_snapshot"])["currentNodeId"] == "x"


def test_pipeline_continues_after_sse_disconnect(isolated_db, monkeypatch):
    """核心红线：SSE 断开后后台管线继续推进快照。"""

    # 用受控的假事件源替换真实管线（单测级 stub，验证接线而非管线本身）
    def fake_stream(*args, **kwargs):
        yield _sse({"type": "analysis_start", "session_id": "x"})
        for nid in ["check_cache", "fetch_data", "validate_financials"]:
            yield _sse({"type": "node_start", "node_id": nid, "layer": "PREP"})
            time.sleep(0.5)
            yield _sse({"type": "node_complete", "node_id": nid, "layer": "PREP", "output": {}})
        yield _sse({"type": "report_ready", "report_markdown": "# ok"})

    monkeypatch.setattr(api_mod, "_run_graph_streaming", fake_stream)

    client = TestClient(app)
    # 发起分析，读到第一个事件即断开
    with client.stream(
        "POST",
        "/api/analyze",
        json={
            "query": "分析贵州茅台",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
        },
    ) as resp:
        sid = None
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("session_id"):
                    sid = ev["session_id"]
                    break
        # 出 with 块即断开连接
    assert sid is not None

    # 等后台推进
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    snap_raw = session_store.get_session(sid)["pipeline_snapshot"]
    assert snap_raw is not None
    snap = json.loads(snap_raw)
    # layerTree 为内嵌的序列化 JSON 字符串，需二次解析得到树结构
    tree = json.loads(snap["layerTree"])
    done_nodes = [
        c["nodeId"] for layer in tree for c in layer["children"] if c["status"] == "completed"
    ]
    # 断开后仍推进到后续节点
    assert "validate_financials" in done_nodes


def test_pipeline_snapshot_persists_after_completion(isolated_db, monkeypatch):
    """管线完成后 snapshot 持久化到 DB，供断线恢复查询。"""

    def fake_stream(*args, **kwargs):
        yield _sse({"type": "analysis_start", "session_id": "x"})
        for nid in ["check_cache", "fetch_data", "validate_financials"]:
            yield _sse({"type": "node_start", "node_id": nid, "layer": "PREP"})
            time.sleep(0.05)
            yield _sse({"type": "node_complete", "node_id": nid, "layer": "PREP", "output": {}})
        yield _sse({"type": "report_ready", "report_markdown": "# ok"})

    monkeypatch.setattr(api_mod, "_run_graph_streaming", fake_stream)

    client = TestClient(app)
    sid = None
    with client.stream(
        "POST",
        "/api/analyze",
        json={
            "query": "分析贵州茅台",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
        },
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("session_id"):
                    sid = ev["session_id"]
                if ev.get("type") == "done":
                    break
    assert sid is not None

    # 等后台线程最终落盘
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    snap_raw = session_store.get_session(sid)["pipeline_snapshot"]
    assert snap_raw is not None
    snap = json.loads(snap_raw)
    # layerTree 为内嵌的序列化 JSON 字符串，需二次解析得到树结构
    tree = json.loads(snap["layerTree"])
    done_nodes = [
        c["nodeId"] for layer in tree for c in layer["children"] if c["status"] == "completed"
    ]
    assert "validate_financials" in done_nodes
    assert snap["progress"] > 0
