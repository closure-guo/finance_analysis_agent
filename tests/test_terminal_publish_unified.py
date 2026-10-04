"""终态发布收拢统一测试（add-event-delivery-resilience Task 4）。

行为契约（task-4-brief）：
- 所有终态事件（done/error/interrupted，report_ready 视同终态关键路径）发布前
  MUST 先冲刷本生产者的 pending 明细缓冲（保 seq 单调），发布 MUST 走
  StreamRegistry.publish_terminal（journal 瞬断重试兜底）
- pending 明细缓冲超过 512 条丢最旧 thinking 并计数（pending_overflow）

场景：
A. fast path 终态走重试发布（PipelineRunner + loop 桥接）
B. pending 超限丢最旧（trim_pending_overflow 纯函数）
C. ReAct done 走 publish_terminal（api._run_react_analysis）
D. ReAct 流内异常显式发布 error 终态且走 publish_terminal
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest

from finance_agent import session_store
from finance_agent.pipeline_runner import PipelineRunner


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _setup_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def _journal_types(sid: str) -> list[str]:
    return [
        json.loads(r["event_json"]).get("type")
        for r in session_store.list_session_events(sid, after_seq=0)
    ]


def _install_terminal_spies(monkeypatch) -> tuple[list[str], list[str]]:
    """在 registry 单例上包一层 spy：记录终态经由（publish_terminal / publish）。

    spy 内部转调真实现，发布行为不变，只旁路记录 event type。
    """
    import finance_agent.stream_registry as sr

    via_terminal: list[str] = []
    via_publish: list[str] = []
    real_terminal = sr.registry.publish_terminal
    real_publish = sr.registry.publish

    async def spy_terminal(session_id, event):
        via_terminal.append(event.get("type"))
        return await real_terminal(session_id, event)

    async def spy_publish(session_id, event):
        if event.get("type") in ("done", "interrupted", "error"):
            via_publish.append(event.get("type"))
        return await real_publish(session_id, event)

    monkeypatch.setattr(sr.registry, "publish_terminal", spy_terminal)
    monkeypatch.setattr(sr.registry, "publish", spy_publish)
    return via_terminal, via_publish


def _start_loop_thread() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """后台事件循环线程：PipelineRunner 的 run_coroutine_threadsafe 桥接目标。"""
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, t


def _wait_runner_done(sid: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)


def _bridge_events():
    """fast path 事件序列：thinking + 节点边界 + report_ready（终态由 finally 发布）。"""
    yield _sse({"type": "analysis_start", "session_id": "s1"})
    yield _sse({"type": "node_start", "node_id": "check_cache", "layer": "PREP"})
    yield _sse({"type": "thinking_token", "token": "读取缓存", "node": "check_cache"})
    yield _sse({"type": "node_complete", "node_id": "check_cache", "layer": "PREP", "output": {}})
    yield _sse({"type": "report_ready", "session_id": "s1", "report_markdown": "# 报告"})


# ── 场景 A：fast path 终态走重试发布 ──


def test_fastpath_terminal_uses_publish_terminal(tmp_path, monkeypatch):
    """done/report_ready MUST 走 publish_terminal；普通 publish 不承载终态。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
    via_terminal, via_publish = _install_terminal_spies(monkeypatch)

    loop, t = _start_loop_thread()
    try:
        PipelineRunner.start(
            sid,
            _bridge_events,
            {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0},
            loop=loop,
        )
        _wait_runner_done(sid)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=5)

    assert not PipelineRunner.is_running(sid)
    # 终态关键路径（report_ready 视同终态 + done）经 publish_terminal 发布
    assert "done" in via_terminal, f"done 应经 publish_terminal 发布: {via_terminal}"
    assert "report_ready" in via_terminal, (
        f"report_ready 应经 publish_terminal 发布: {via_terminal}"
    )
    # 普通 publish 未承载任何终态事件
    assert via_publish == [], f"终态不得走普通 publish: {via_publish}"
    # journal 尾部：report_ready 先于 done（先冲刷 pending 保 seq 单调）
    types = _journal_types(sid)
    assert types[-1] == "done", f"journal 尾事件应为 done: {types}"
    assert "report_ready" in types and types.index("report_ready") < len(types) - 1
    rows = session_store.list_session_events(sid, after_seq=0)
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq 必须单调无重号"


def test_fastpath_terminal_publish_failure_does_not_hang_runner(tmp_path, monkeypatch):
    """终态发布通道整体失败（publish_terminal 重试耗尽 raise）时 state.done 仍须置位。

    publish_terminal 契约：重试耗尽显式 raise，由调用方日志兜底。若 finally 中
    外抛跳过 state.done 置位，is_running 永真、会话永远无法重开。
    """
    import finance_agent.stream_registry as sr

    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    async def broken_publish(session_id, event):
        raise ConnectionError("journal 不可用")

    monkeypatch.setattr(sr.registry, "publish_terminal", broken_publish)
    monkeypatch.setattr(sr.registry, "publish", broken_publish)

    loop, t = _start_loop_thread()
    try:
        PipelineRunner.start(
            sid,
            _bridge_events,
            {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0},
            loop=loop,
        )
        _wait_runner_done(sid)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=5)

    assert not PipelineRunner.is_running(sid), (
        "终态发布失败不得悬挂 is_running（state.done 必须置位）"
    )
    # 全部发布通道失败 → journal 无终态（显式失败已被日志兜底，不留半终态）
    assert "done" not in _journal_types(sid)


# ── 场景 B：pending 超限丢最旧 ──


def test_pending_overflow_drops_oldest_and_counts(caplog):
    """pending 超 512 条：flush 前丢最旧至上限，record_drop(pending_overflow) 计数。"""
    from finance_agent.pipeline_runner import PENDING_TOKEN_MAX, trim_pending_overflow

    pending = [{"type": "thinking_token", "token": f"t{i}"} for i in range(600)]
    drops: list[tuple[str, str]] = []
    dropped_total = [0]

    with caplog.at_level("WARNING", logger="finance_agent.pipeline_runner"):
        dropped = trim_pending_overflow(
            pending, "sid-x", lambda s, k: drops.append((s, k)), dropped_total
        )

    assert dropped == 600 - PENDING_TOKEN_MAX
    # 队列长度守恒到上限
    assert len(pending) == PENDING_TOKEN_MAX
    # 丢的是最旧：t0..t(overflow-1) 被丢弃，保留尾部
    assert pending[0]["token"] == f"t{dropped}"
    assert pending[-1]["token"] == f"t{599}"
    # 丢弃计数递增
    assert drops == [("sid-x", "pending_overflow")]
    assert dropped_total[0] == dropped
    # 首条丢弃有 WARNING 日志
    assert any("sid-x" in r.getMessage() for r in caplog.records), "首条丢弃应有 WARNING"

    # 再次超限：累计计数继续递增
    pending2 = [{"type": "thinking_token", "token": "x"} for _ in range(PENDING_TOKEN_MAX + 100)]
    dropped2 = trim_pending_overflow(
        pending2, "sid-x", lambda s, k: drops.append((s, k)), dropped_total
    )
    assert dropped2 == 100
    assert len(pending2) == PENDING_TOKEN_MAX
    assert dropped_total[0] == dropped + 100
    assert drops == [("sid-x", "pending_overflow"), ("sid-x", "pending_overflow")]


def test_pending_overflow_noop_under_limit():
    """未超限时 trim 为无操作：不丢弃、不计数。"""
    from finance_agent.pipeline_runner import PENDING_TOKEN_MAX, trim_pending_overflow

    pending = [{"type": "thinking_token", "token": "t"} for _ in range(10)]
    drops: list[tuple[str, str]] = []
    dropped = trim_pending_overflow(pending, "sid", lambda s, k: drops.append((s, k)), [0])
    assert dropped == 0
    assert len(pending) == 10
    assert drops == []
    assert PENDING_TOKEN_MAX == 512


# ── 场景 C：ReAct done 走 publish_terminal ──


@pytest.mark.asyncio
async def test_react_done_uses_publish_terminal(tmp_path, monkeypatch):
    """api._run_react_analysis 的 done/report_ready MUST 走 publish_terminal。"""
    import time as time_mod

    import finance_agent.agent_factory as agent_factory
    import finance_agent.api as api_mod

    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    via_terminal, via_publish = _install_terminal_spies(monkeypatch)

    async def fake_stream(agent, user_input, **kwargs):
        yield "data: " + json.dumps({"type": "thinking_token", "token": "思考"}) + "\n\n"
        yield "data: " + json.dumps({"type": "report_ready", "report_markdown": "# 报告"}) + "\n\n"

    monkeypatch.setattr(agent_factory, "build_agent", lambda **kw: object())
    monkeypatch.setattr(agent_factory, "stream_agent_to_sse", fake_stream)

    req = api_mod.AnalyzeRequest(query="测试终态收拢")
    await api_mod._run_react_analysis(sid, req, "aid", time_mod.time(), None, None)

    assert "done" in via_terminal, f"done 应经 publish_terminal 发布: {via_terminal}"
    assert "report_ready" in via_terminal, (
        f"report_ready 应经 publish_terminal 发布: {via_terminal}"
    )
    assert via_publish == [], f"终态不得走普通 publish: {via_publish}"

    types = _journal_types(sid)
    assert types[-1] == "done", f"journal 尾事件应为 done: {types}"
    # 终态发布前 pending 已冲刷：thinking_token 先于 done 落库
    assert "thinking_token" in types
    rows = session_store.list_session_events(sid, after_seq=0)
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq 必须单调无重号"


@pytest.mark.asyncio
async def test_react_exception_publishes_error_via_terminal(tmp_path, monkeypatch):
    """ReAct 流内异常：error 终态 MUST 显式落 journal 且走 publish_terminal。

    原实现 error 终态仅由 registry._run_task 兜底（普通 publish，无重试），
    且 pending 残余 token 不冲刷即丢失。
    """
    import time as time_mod

    import finance_agent.agent_factory as agent_factory
    import finance_agent.api as api_mod

    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    via_terminal, _via_publish = _install_terminal_spies(monkeypatch)

    async def fake_stream(agent, user_input, **kwargs):
        yield "data: " + json.dumps({"type": "thinking_token", "token": "思考"}) + "\n\n"
        raise RuntimeError("模拟 ReAct 异常")

    monkeypatch.setattr(agent_factory, "build_agent", lambda **kw: object())
    monkeypatch.setattr(agent_factory, "stream_agent_to_sse", fake_stream)

    req = api_mod.AnalyzeRequest(query="测试异常终态")
    with pytest.raises(RuntimeError, match="模拟 ReAct 异常"):
        await api_mod._run_react_analysis(sid, req, "aid", time_mod.time(), None, None)

    assert "error" in via_terminal, f"error 应经 publish_terminal 发布: {via_terminal}"

    types = _journal_types(sid)
    assert "error" in types, f"error 终态必须显式落 journal: {types}"
    # 终态发布前 pending 已冲刷：异常前的 thinking_token 不丢失
    assert "thinking_token" in types, f"异常前缓冲的 token 应回收: {types}"
    assert types.index("thinking_token") < types.index("error")

    row = session_store.get_session(sid)
    assert row["status"] == "failed"
    assert "模拟 ReAct 异常" in (row["failure_reason"] or "")


@pytest.mark.asyncio
async def test_react_early_exception_still_publishes_error(tmp_path, monkeypatch):
    """try 体内早期异常（流启动前，如 build_agent 抛错）也 MUST 发布 error 终态。

    冲刷助手与缓冲声明若在 try 体内定义，早期异常时 except 分支的
    _flush_tokens 会 NameError 短路，error 终态无法发布。
    """
    import time as time_mod

    import finance_agent.agent_factory as agent_factory
    import finance_agent.api as api_mod

    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    via_terminal, _via_publish = _install_terminal_spies(monkeypatch)

    def _boom(**kw):
        raise RuntimeError("build_agent 失败")

    monkeypatch.setattr(agent_factory, "build_agent", _boom)

    req = api_mod.AnalyzeRequest(query="早期异常")
    with pytest.raises(RuntimeError, match="build_agent 失败"):
        await api_mod._run_react_analysis(sid, req, "aid", time_mod.time(), None, None)

    assert "error" in via_terminal, f"早期异常的 error 也应经 publish_terminal: {via_terminal}"
    assert "error" in _journal_types(sid)
