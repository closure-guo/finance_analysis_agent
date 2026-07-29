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
