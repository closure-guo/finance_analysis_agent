"""ReAct 路径后台化测试。

对应 change: harden-react-path-resilience Task 3.1。
验证 SSE 断开（generator 关闭）后，后台 Task 继续执行并更新会话状态。
"""

from __future__ import annotations

import pytest

from finance_agent import session_store
from finance_agent.agent_factory import _make_run_deep_analysis


def _mock_stream_events():
    """返回模拟的 graph.stream 事件序列（含至少一个节点完成 + 最终报告）。"""
    yield ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000})
    yield ("updates", {"check_cache": {"cached": True}})
    yield ("custom", {"type": "node_end", "node": "check_cache", "ts": 1001, "duration_ms": 1})
    yield ("updates", {"generate_report": {"final_report": "# 测试报告\n内容"}})


@pytest.mark.asyncio
async def test_generator_close_does_not_abort_pipeline(tmp_path, monkeypatch):
    """SSE 断开（aclose）后，后台 Task SHALL 继续执行，会话最终为 completed。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    monkeypatch.setattr(
        "finance_agent.agent_factory._stream_graph",
        lambda initial_state, config=None, session_id=None: _mock_stream_events(),
    )

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    # 消费第一个事件后关闭 generator（模拟 SSE 断开）
    gen = run_deep_analysis("600519", "贵州茅台")
    first_event = await gen.__anext__()
    assert first_event is not None
    await gen.aclose()

    # 等待后台 Task 完成
    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    # 验证会话状态最终为 completed
    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "completed"


@pytest.mark.asyncio
async def test_generator_close_pipeline_snapshot_persisted(tmp_path, monkeypatch):
    """SSE 断开后，pipeline_snapshot SHALL 持续更新（后台 Task 写入快照）。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    monkeypatch.setattr(
        "finance_agent.agent_factory._stream_graph",
        lambda initial_state, config=None, session_id=None: _mock_stream_events(),
    )

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    gen = run_deep_analysis("600519", "贵州茅台")
    await gen.__anext__()
    await gen.aclose()

    # 等待后台 Task 完成
    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    # 验证快照已写入
    row = session_store.get_session(sid)
    assert row is not None
    assert row["pipeline_snapshot"] is not None


@pytest.mark.asyncio
async def test_pipeline_failure_sets_failure_reason(tmp_path, monkeypatch):
    """后台 Task 异常时 SHALL 设置 failed + failure_reason。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    def _failing_stream(initial_state, config=None, session_id=None):
        yield ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000})
        raise RuntimeError("模拟管线异常")

    monkeypatch.setattr("finance_agent.agent_factory._stream_graph", _failing_stream)

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    gen = run_deep_analysis("600519", "贵州茅台")
    await gen.__anext__()
    await gen.aclose()

    # 等待后台 Task 完成
    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    # 验证失败状态和原因
    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "failed"
    assert row["failure_reason"] is not None
    assert "模拟管线异常" in row["failure_reason"]
