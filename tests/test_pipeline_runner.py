"""PipelineRunner 后台执行器测试。

对应 change: resume-pipeline-across-sessions Task 2。
验证：
- start 幂等，后台线程跑完事件源后 is_running 归 False
- 事件经 get_events 消费式取走
- 节点事件驱动 pipeline_snapshot 持久化（layerTree 状态推进）
- mark_swept_failed 将悬挂 running 会话置 failed
"""

from __future__ import annotations

import json
import time

from finance_agent import session_store
from finance_agent.pipeline_runner import PipelineRunner


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _fake_events():
    """模拟 _run_graph_streaming 的 SSE 事件序列（两节点 + 完成）。"""
    yield _sse({"type": "analysis_start", "session_id": "s1"})
    yield _sse({"type": "node_start", "node_id": "check_cache", "layer": "PREP"})
    yield _sse(
        {
            "type": "node_complete",
            "node_id": "check_cache",
            "layer": "PREP",
            "completed": ["check_cache"],
            "progress": 0.03,
            "output": {"summary": "ok"},
        }
    )
    yield _sse({"type": "node_start", "node_id": "fetch_data", "layer": "PREP"})
    yield _sse(
        {
            "type": "node_complete",
            "node_id": "fetch_data",
            "layer": "PREP",
            "completed": ["check_cache", "fetch_data"],
            "progress": 0.06,
            "output": {},
        }
    )
    yield _sse({"type": "report_ready", "session_id": "s1", "report_markdown": "# 报告"})


def test_start_idempotent_and_events_accumulate(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    PipelineRunner.start(
        sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0}
    )
    PipelineRunner.start(
        sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0}
    )  # 幂等不重复启动

    # 等后台线程跑完
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)
    assert not PipelineRunner.is_running(sid)

    events = PipelineRunner.get_events(sid)
    assert any('"node_start"' in e for e in events)
    assert any('"report_ready"' in e for e in events)

    # 快照已持久化
    row = session_store.get_session(sid)
    snap = json.loads(row["pipeline_snapshot"])
    assert snap["currentNodeId"] in ("", "fetch_data")
    assert snap["progress"] > 0


def test_snapshot_tracks_node_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    PipelineRunner.start(
        sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0}
    )
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    snap = json.loads(session_store.get_session(sid)["pipeline_snapshot"])
    # layerTree 为内嵌的序列化 JSON 字符串，需二次解析得到树结构
    tree = json.loads(snap["layerTree"])
    all_children = [c for layer in tree for c in layer["children"]]
    by_id = {c["nodeId"]: c for c in all_children}
    assert by_id["check_cache"]["status"] == "completed"
    assert by_id["fetch_data"]["status"] == "completed"


def test_sweep_marks_running_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
    n = PipelineRunner.mark_swept_failed()
    assert n >= 1
    assert session_store.get_session(sid)["status"] == "failed"


def _failing_events():
    """迭代中途抛异常的事件源。"""
    yield _sse({"type": "node_start", "node_id": "check_cache", "layer": "prep"})
    raise RuntimeError("模拟事件源异常")


def test_event_source_exception_marks_failed(tmp_path, monkeypatch):
    """事件源迭代中抛异常 → session 置 failed 且 is_running 归 False。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    PipelineRunner.start(
        sid,
        _failing_events,
        {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0},
    )
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    assert not PipelineRunner.is_running(sid)
    assert session_store.get_session(sid)["status"] == "failed"


def test_get_events_cleanup_after_done(tmp_path, monkeypatch):
    """管线跑完后 get_events 消费取空 → _running 条目被清理。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    PipelineRunner.start(
        sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0}
    )
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    # 第一次取走全部累积事件；第二次取空触发清理
    assert PipelineRunner.get_events(sid)
    assert PipelineRunner.get_events(sid) == []
    assert sid not in PipelineRunner._running
