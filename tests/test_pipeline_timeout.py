"""管线全局超时测试。

对应 change: harden-react-path-resilience Task 5.1。
验证管线执行超过配置超时时间后 SHALL 设置 failed + failure_reason。
"""

from __future__ import annotations

import time

import pytest

from finance_agent import session_store
from finance_agent.agent_factory import _make_run_deep_analysis


@pytest.mark.asyncio
async def test_pipeline_timeout_sets_failed(tmp_path, monkeypatch):
    """管线超过 PIPELINE_TIMEOUT_SECONDS 后 SHALL 设置 failed + failure_reason。"""
    # 设置 0.5 秒超时
    monkeypatch.setenv("PIPELINE_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    # Mock：第一个事件后 sleep 2 秒，超过 0.5 秒超时
    def _slow_stream(initial_state, config=None, session_id=None):
        yield ("custom", {"type": "node_start", "node": "check_cache", "ts": 1000})
        time.sleep(2)  # 模拟慢速节点，超过超时
        yield ("updates", {"check_cache": {"cached": True}})

    monkeypatch.setattr("finance_agent.agent_factory._stream_graph", _slow_stream)

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    gen = run_deep_analysis("600519", "贵州茅台")
    await gen.__anext__()  # 消费第一个事件
    await gen.aclose()  # 关闭 generator（模拟 SSE 断开）

    # 等待后台 Task 完成（超时会触发 TimeoutError）
    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "failed"
    assert row["failure_reason"] is not None
    assert "超时" in row["failure_reason"]
