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


@pytest.mark.asyncio
async def test_pipeline_wall_clock_timeout_triggers_despite_steady_chunks(tmp_path, monkeypatch):
    """墙钟超时：chunk 持续到达（空闲永不超时）但总时长超预算 SHALL 判超时。

    修复前 wait_for(chunk_queue.get(), timeout=...) 是单次空闲超时——
    thinking token 持续流动时永不触发，线上 601700 深研管线跑了 71 分钟
    无人拦截。spec pipeline-events「管线超时与中断检测」要求自管线启动
    起算的全局执行时间超限即终止并标 failed。
    """
    monkeypatch.setenv("PIPELINE_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    def _steady_stream(initial_state, config=None, session_id=None):
        # 持续小间隔 chunk：任何相邻间隔（0.05s）远小于 0.5s 空闲阈值，
        # 但总时长 ~2s 超过 0.5s 全局预算
        for i in range(40):
            yield ("custom", {"type": "thinking", "node": "trader", "token": f"t{i}"})
            time.sleep(0.05)

    monkeypatch.setattr("finance_agent.agent_factory._stream_graph", _steady_stream)

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    gen = run_deep_analysis("600519", "贵州茅台")
    await gen.__anext__()  # 消费第一个事件
    await gen.aclose()  # 关闭 generator（模拟 SSE 断开，后台任务继续）

    from finance_agent.agent_factory import _background_tasks

    bg_task = _background_tasks.get(sid)
    if bg_task is not None:
        await bg_task

    row = session_store.get_session(sid)
    assert row is not None
    assert row["status"] == "failed", "持续产出但总时长超预算的管线应被判超时"
    assert row["failure_reason"] is not None
    assert "超时" in row["failure_reason"]


@pytest.mark.asyncio
async def test_pipeline_timeout_emits_tool_result(tmp_path, monkeypatch):
    """超时 SHALL 发 TOOL_RESULT：空结果会让 Agent 误判「临时故障」盲目重试。

    线上事故（601700 复盘）：墙钟超时只发 PROGRESS 不发 TOOL_RESULT，Agent
    上下文里工具结果为空，重试意图只能以方舟文本格式泄漏（见 incident 020）。
    """
    monkeypatch.setenv("PIPELINE_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    def _steady_stream(initial_state, config=None, session_id=None):
        for i in range(40):
            yield ("custom", {"type": "thinking", "node": "trader", "token": f"t{i}"})
            time.sleep(0.05)

    monkeypatch.setattr("finance_agent.agent_factory._stream_graph", _steady_stream)

    run_deep_analysis = _make_run_deep_analysis(api_key="fake", session_id=sid)

    async def _collect():
        events = []
        async for ev in run_deep_analysis("600519", "贵州茅台"):
            events.append(ev)
        return events

    events = await _collect()

    tool_results = [e for e in events if e.event_type.value == "tool_result"]
    assert tool_results, (
        "超时后必须下发 TOOL_RESULT（含超时原因），否则 Agent 拿到空结果"
        f"无法向用户解释失败。实际事件: {[e.event_type for e in events]}"
    )
    assert "超时" in (tool_results[-1].tool_result.output if tool_results[-1].tool_result else "")


@pytest.mark.asyncio
async def test_pipeline_timeout_stops_producer_thread(tmp_path, monkeypatch):
    """超时后生产端线程 SHALL 协作式停止拉流，不得孤儿式跑完全部节点。

    601700 复盘：墙钟超时触发后，executor 线程里的 graph.stream 无人叫停，
    R2 分析师继续烧了 3 分钟 LLM 调用（spec pipeline-events：超时 SHALL
    终止管线执行）。
    """
    monkeypatch.setenv("PIPELINE_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    pulled = {"n": 0}

    def _steady_stream(initial_state, config=None, session_id=None):
        for i in range(40):
            pulled["n"] += 1
            yield ("custom", {"type": "thinking", "node": "trader", "token": f"t{i}"})
            time.sleep(0.05)

    monkeypatch.setattr("finance_agent.agent_factory._stream_graph", _steady_stream)

    tool = _make_run_deep_analysis(api_key="fake", session_id=sid)
    t0 = time.time()
    async for _ev in tool("600519", "贵州茅台"):
        pass
    elapsed = time.time() - t0

    # 40 条 × 50ms 全量约 2s；超时 0.5s + 取消检查间隔后应停在 ~13 条
    assert pulled["n"] < 20, f"取消后生产端仍在拉流: pulled={pulled['n']}"
    assert elapsed < 1.5, f"工具应在超时后立即结束而非等完全部流: {elapsed:.2f}s"
