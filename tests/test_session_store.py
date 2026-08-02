"""session_store pipeline_snapshot 列与读写测试。

对应 change: resume-pipeline-across-sessions Task 1。
验证 sessions 表新增 pipeline_snapshot 列后的读写行为：
- update_pipeline_snapshot 写入 JSON 快照
- get_session 返回的 dict 自动包含 pipeline_snapshot 键（未反序列化）
"""

from __future__ import annotations

import json

from finance_agent import session_store


def test_pipeline_snapshot_roundtrip(tmp_path, monkeypatch):
    """写入快照后，get_session 应返回一致的 JSON 文本。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    snapshot = {
        "layerTree": [],
        "currentNodeId": "trader",
        "progress": 0.5,
        "updatedAt": 123,
    }
    assert session_store.update_pipeline_snapshot(sid, snapshot) is True

    row = session_store.get_session(sid)
    assert row is not None
    assert json.loads(row["pipeline_snapshot"]) == snapshot


def test_pipeline_snapshot_default_none(tmp_path, monkeypatch):
    """未写入快照的会话，pipeline_snapshot 应为 None。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")
    row = session_store.get_session(sid)
    assert row["pipeline_snapshot"] is None


def test_pipeline_timelines_roundtrip(tmp_path, monkeypatch):
    """写入管线时序后，get_session 返回反序列化 dict。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    timelines = {
        "bull_debater": [
            {"type": "thinking", "content": "看多逻辑", "done": True},
            {"type": "tool_call", "name": "get_news", "args": "{}", "result": "新闻", "done": True},
        ]
    }
    assert session_store.update_pipeline_timelines(sid, timelines) is True

    row = session_store.get_session(sid)
    assert row is not None
    assert row["pipeline_timelines"] == timelines


def test_pipeline_timelines_default_none(tmp_path, monkeypatch):
    """未写入的会话，pipeline_timelines 应为 None。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")
    row = session_store.get_session(sid)
    assert row["pipeline_timelines"] is None


def test_append_chat_with_agent_timeline(tmp_path, monkeypatch):
    """append_chat 传入 agent_timeline 时，条目应含 agentTimeline 字段。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台")

    timeline = [
        {"type": "thinking", "content": "分析中", "done": True},
        {"type": "search", "query": "贵州茅台 财报", "results": [], "status": "done"},
    ]
    session_store.append_chat(sid, "assistant", "结论", thinking="分析中", agent_timeline=timeline)

    row = session_store.get_session(sid)
    history = row["chat_history"]
    assert history[0]["agentTimeline"] == timeline
    assert history[0]["thinking"] == "分析中"


def test_append_chat_without_agent_timeline_backward_compat(tmp_path, monkeypatch):
    """不传 agent_timeline 时（旧调用方），条目不含 agentTimeline 键。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台")

    session_store.append_chat(sid, "assistant", "结论", thinking="分析中")
    row = session_store.get_session(sid)
    assert "agentTimeline" not in row["chat_history"][0]


def test_failure_reason_roundtrip(tmp_path, monkeypatch):
    """update_session_status 传入 failure_reason 后，get_session 应返回正确值。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    assert session_store.update_session_status(sid, "failed", failure_reason="管线执行超时") is True

    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "failed"
    assert row["failure_reason"] == "管线执行超时"


def test_failure_reason_default_none(tmp_path, monkeypatch):
    """不传 failure_reason 时，列值应为 None。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    session_store.update_session_status(sid, "completed")

    row = session_store.get_session(sid)
    assert row is not None
    assert row["failure_reason"] is None


def test_failure_reason_overwrite(tmp_path, monkeypatch):
    """多次更新 failure_reason，最后一次生效。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    session_store.update_session_status(sid, "failed", failure_reason="第一次失败")
    session_store.update_session_status(sid, "failed", failure_reason="第二次失败")

    row = session_store.get_session(sid)
    assert row["failure_reason"] == "第二次失败"
