"""ReAct 主链路（run_deep_analysis 工具）管线快照与会话状态兜底测试。

对应 change: resume-pipeline-across-sessions Task 5.5。
验证：
- 快照推进：消费过程中/后 pipeline_snapshot 可解析，已发 node_complete 的节点
  status=completed，progress > 0
- 状态流转：工具入口置 running，循环正常结束置 completed
- 异常置 failed：stub _stream_graph 抛异常 → 工具 re-raise + status=failed
- 事件流不变：StreamEvent 的 sse_type 序列与无快照逻辑时一致
"""

from __future__ import annotations

import asyncio
import json

import pytest

from finance_agent import agent_factory, session_store

# ───────────────────────────────────────────────
# 测试夹具与工具
# ───────────────────────────────────────────────


def _make_session(tmp_path, monkeypatch, status: str = "running") -> str:
    """在临时 DB 上创建会话，返回 session_id。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return session_store.create_session(stock_code="600519", stock_name="贵州茅台", status=status)


def _consume_tool(tool, *args, **kwargs):
    """同步驱动异步生成器工具，收集所有 StreamEvent。"""

    async def _run():
        events = []
        async for ev in tool(*args, **kwargs):
            events.append(ev)
        return events

    return asyncio.run(_run())


def _consume_tool_expect_error(tool, *args, **kwargs):
    """同步驱动工具并捕获异常。"""

    async def _run():
        events = []
        with pytest.raises(RuntimeError):
            async for ev in tool(*args, **kwargs):
                events.append(ev)
        return events

    return asyncio.run(_run())


def _snapshot(session_id: str) -> dict:
    """读取并解析会话的 pipeline_snapshot。"""
    row = session_store.get_session(session_id)
    return json.loads(row["pipeline_snapshot"])


def _snapshot_node_status(snapshot: dict, node_id: str) -> str:
    # layerTree 为内嵌的序列化 JSON 字符串，需二次解析得到树结构
    tree = json.loads(snapshot["layerTree"])
    for layer in tree:
        for child in layer["children"]:
            if child["nodeId"] == node_id:
                return child["status"]
    raise AssertionError(f"node {node_id} not in snapshot layerTree")


# ───────────────────────────────────────────────
# stub _stream_graph：产出受控事件序列
# ───────────────────────────────────────────────

# 两个节点的受控序列：
#   updates: check_cache（首次出现 → node_start + node_complete）
#   custom:  check_cache node_end → node_timing
#   updates: fetch_data（首次出现 → node_start + node_complete）
#   custom:  fetch_data node_end → node_timing
_FAKE_CHUNKS: list[tuple[str, dict]] = [
    ("updates", {"check_cache": {"summary": "数据就绪"}}),
    ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000}),
    ("custom", {"type": "node_end", "node": "check_cache", "ts": 1500, "duration_ms": 500}),
    ("updates", {"fetch_data": {"summary": "行情获取完成"}}),
    ("custom", {"type": "node_start", "node": "fetch_data", "ts": 1600}),
    ("custom", {"type": "node_end", "node": "fetch_data", "ts": 2200, "duration_ms": 600}),
]


def _stub_stream_graph(initial_state, config=None, session_id=None):
    """替换 _stream_graph 的同步生成器，产出受控 (mode, chunk) 序列。"""
    yield from _FAKE_CHUNKS


# 无快照逻辑时的基准 sse_type 序列（来自现有实现语义推导）：
#   check_cache: node_start, node_complete
#   check_cache custom node_end: node_timing
#   fetch_data:  node_start, node_complete
#   fetch_data custom node_end: node_timing
#   结束: report_ready (TOOL_RESULT)
_BASELINE_SSE_TYPES = [
    "node_start",
    "node_complete",
    "node_timing",
    "node_start",
    "node_complete",
    "node_timing",
    "report_ready",
]


def _sse_types(events) -> list[str]:
    """提取 StreamEvent 序列的 sse_type 序列。"""
    out = []
    for ev in events:
        meta = (ev.metadata or {}) if hasattr(ev, "metadata") else {}
        if hasattr(ev, "tool_result") and ev.tool_result and ev.tool_result.metadata:
            out.append(ev.tool_result.metadata.get("sse_type", ""))
        else:
            out.append(meta.get("sse_type", ""))
    return out


# ───────────────────────────────────────────────
# 测试用例
# ───────────────────────────────────────────────


def test_snapshot_progresses_during_consumption(tmp_path, monkeypatch):
    """消费结束后快照可解析，已发 node_complete 的节点 status=completed，progress > 0。"""
    sid = _make_session(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_factory, "_stream_graph", _stub_stream_graph)

    tool = agent_factory._make_run_deep_analysis(session_id=sid)
    _consume_tool(tool, "600519", "贵州茅台")

    snap = _snapshot(sid)
    assert snap["progress"] > 0
    assert _snapshot_node_status(snap, "check_cache") == "completed"
    assert _snapshot_node_status(snap, "fetch_data") == "completed"


def test_status_transitions_to_completed(tmp_path, monkeypatch):
    """工具正常结束后 session status == 'completed'。"""
    sid = _make_session(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_factory, "_stream_graph", _stub_stream_graph)

    tool = agent_factory._make_run_deep_analysis(session_id=sid)
    _consume_tool(tool, "600519", "贵州茅台")

    assert session_store.get_session(sid)["status"] == "completed"


def test_status_running_during_execution(tmp_path, monkeypatch):
    """stub _stream_graph 迭代期间 session status 应为 running（入口兜底）。"""
    sid = _make_session(tmp_path, monkeypatch, status="pending")
    observed: list[str] = []

    def _spy_stream_graph(initial_state, config=None, session_id=None):
        # 在管线事件流产出前捕获会话状态
        observed.append(session_store.get_session(sid)["status"])
        yield from _FAKE_CHUNKS

    monkeypatch.setattr(agent_factory, "_stream_graph", _spy_stream_graph)

    tool = agent_factory._make_run_deep_analysis(session_id=sid)
    _consume_tool(tool, "600519", "贵州茅台")

    assert observed == ["running"]


def test_exception_marks_failed_and_reraises(tmp_path, monkeypatch):
    """stub _stream_graph 抛异常 → 工具 re-raise + status=failed。"""
    sid = _make_session(tmp_path, monkeypatch)

    def _failing_stream_graph(initial_state, config=None, session_id=None):
        yield ("updates", {"check_cache": {}})
        raise RuntimeError("模拟管线异常")

    monkeypatch.setattr(agent_factory, "_stream_graph", _failing_stream_graph)

    tool = agent_factory._make_run_deep_analysis(session_id=sid)
    _consume_tool_expect_error(tool, "600519", "贵州茅台")

    assert session_store.get_session(sid)["status"] == "failed"


def test_event_stream_unchanged(tmp_path, monkeypatch):
    """接入快照逻辑后，StreamEvent 的 sse_type 序列与基准序列一致。"""
    sid = _make_session(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_factory, "_stream_graph", _stub_stream_graph)

    tool = agent_factory._make_run_deep_analysis(session_id=sid)
    events = _consume_tool(tool, "600519", "贵州茅台")

    assert _sse_types(events) == _BASELINE_SSE_TYPES


def test_no_session_id_skips_snapshot(tmp_path, monkeypatch):
    """session_id 为空时跳过快照/状态写入，行为与现状一致（不报错）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    monkeypatch.setattr(agent_factory, "_stream_graph", _stub_stream_graph)

    tool = agent_factory._make_run_deep_analysis(session_id=None)
    events = _consume_tool(tool, "600519", "贵州茅台")

    assert _sse_types(events) == _BASELINE_SSE_TYPES


# ───────────────────────────────────────────────
# 管线时序持久化（persist-full-session-timeline Task 3）
# ───────────────────────────────────────────────

# 含 thinking chunk（custom ctype=='thinking'，带 node）的受控序列
_FAKE_CHUNKS_WITH_THINKING: list[tuple[str, dict]] = [
    ("custom", {"type": "node_start", "node": "check_cache", "ts": 900}),
    ("custom", {"type": "thinking", "node": "check_cache", "token": "读取缓存"}),
    ("updates", {"check_cache": {"summary": "数据就绪"}}),
    ("custom", {"type": "thinking", "node": "check_cache", "token": "…命中"}),
    ("custom", {"type": "node_end", "node": "check_cache", "ts": 1500, "duration_ms": 600}),
    ("custom", {"type": "thinking", "node": "fetch_data", "token": "拉取行情"}),
    ("updates", {"fetch_data": {"summary": "行情获取完成"}}),
    ("custom", {"type": "node_end", "node": "fetch_data", "ts": 2200, "duration_ms": 700}),
]


def _stub_stream_graph_with_thinking(initial_state, config=None, session_id=None):
    yield from _FAKE_CHUNKS_WITH_THINKING


def test_pipeline_timelines_grouped_by_node(tmp_path, monkeypatch):
    """custom 流 thinking chunk 按 node 累积；updates 流 node_complete 收口。"""
    sid = _make_session(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_factory, "_stream_graph", _stub_stream_graph_with_thinking)

    tool = agent_factory._make_run_deep_analysis(session_id=sid)
    _consume_tool(tool, "600519", "贵州茅台")

    timelines = session_store.get_session(sid)["pipeline_timelines"]
    assert timelines["check_cache"] == [
        {"type": "thinking", "content": "读取缓存…命中", "done": True}
    ]
    assert timelines["fetch_data"] == [{"type": "thinking", "content": "拉取行情", "done": True}]


def test_pipeline_timelines_skipped_without_session_id(tmp_path, monkeypatch):
    """session_id 为空时不写 pipeline_timelines（事件流不变）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    monkeypatch.setattr(agent_factory, "_stream_graph", _stub_stream_graph_with_thinking)

    tool = agent_factory._make_run_deep_analysis(session_id=None)
    events = _consume_tool(tool, "600519", "贵州茅台")

    # thinking 事件仍正常透传（sse_type 为空、无 progress 标记）
    assert any(ev.event_type.value == "think" for ev in events)
