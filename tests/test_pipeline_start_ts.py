"""fix-analysis-ux-polish Task 1：管线快照携带 pipeline_start_ts。

后端快照 SHALL 含 pipeline_start_ts（管线启动毫秒时间戳），供前端刷新重建
running 管线时还原「已用时」计时，避免刷新归零。
"""

from __future__ import annotations

import json

import pytest

from finance_agent import session_store
from finance_agent.agent_factory import _make_run_deep_analysis


def _parse_snapshot(session: dict) -> dict:
    snap = session.get("pipeline_snapshot")
    return json.loads(snap) if isinstance(snap, str) else (snap or {})


def _mock_stream_with_node():
    """node_start 触发 _persist_snapshot 落库。"""
    yield ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000})
    yield ("updates", {"check_cache": {"cached": True}})
    yield ("custom", {"type": "node_end", "node": "check_cache", "ts": 1001, "duration_ms": 1})
    yield ("updates", {"generate_report": {"final_report": "# 报告"}})


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


def test_snapshot_roundtrip_preserves_pipeline_start_ts(isolated_db):
    """session_store 快照存取透传 pipeline_start_ts 字段。"""
    sid = session_store.create_session(stock_code="600449", stock_name="宁夏建材", status="running")
    session_store.update_pipeline_snapshot(
        sid,
        {
            "layerTree": "[]",
            "currentNodeId": "prepare",
            "progress": 0.1,
            "updatedAt": 2000,
            "pipeline_start_ts": 1000,
        },
    )
    session = session_store.get_session(sid)
    assert session is not None
    snap = _parse_snapshot(session)
    assert snap.get("pipeline_start_ts") == 1000


@pytest.mark.asyncio
async def test_react_snapshot_includes_pipeline_start_ts(isolated_db, monkeypatch):
    """ReAct 路径 _persist_snapshot 写出的快照含 pipeline_start_ts（<= updatedAt）。"""
    sid = session_store.create_session(stock_code="600449", stock_name="宁夏建材", status="running")
    monkeypatch.setattr(
        "finance_agent.agent_factory._stream_graph",
        lambda initial_state, config=None, session_id=None: _mock_stream_with_node(),
    )

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)
    async for _ in run_deep_analysis("600449", "宁夏建材"):
        pass

    from finance_agent.agent_factory import _background_tasks

    bg = _background_tasks.get(sid)
    if bg is not None:
        await bg

    session = session_store.get_session(sid)
    assert session is not None
    snap = _parse_snapshot(session)
    assert snap, "快照未落库"
    assert "pipeline_start_ts" in snap, "快照缺 pipeline_start_ts"
    assert isinstance(snap["pipeline_start_ts"], int)
    # 启动时间戳应不晚于快照更新时间
    assert snap["pipeline_start_ts"] <= snap["updatedAt"]
