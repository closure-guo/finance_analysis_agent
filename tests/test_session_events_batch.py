"""批量 journal 写入：修复「事件消费被单条 SQLite 事务限速」的假卡死。

线上事故（2026-08-25 601700 深研）：SSE 事件逐条落库（容器实测单条
76ms，运行中含锁竞争 ~860ms/条），2.9 万条 thinking_token 把
report_ready/done 终态事件压在积压尾部——管线 22:54 已完成产出报告，
会话却永远 running、前端永远等不到。批量接口把 N 条事件合并为单事务，
保持「先落库、seq 单调、再按序 fan-out」的既有契约
（session-streaming spec: Stream Event Journal）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from finance_agent import session_store, stream_registry


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


# ── session_store.append_session_events ──


def test_batch_append_assigns_contiguous_seqs(tmp_path, monkeypatch):
    """批量写入返回连续递增 seq，事件按序可读。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    seqs = session_store.append_session_events(
        sid,
        [{"type": "thinking_token", "token": "a"}, {"type": "thinking_token", "token": "b"}],
    )
    assert seqs == [1, 2]

    rows = session_store.list_session_events(sid, after_seq=0)
    assert [r["seq"] for r in rows] == [1, 2]


def test_batch_append_interleaves_with_single_monotonically(tmp_path, monkeypatch):
    """批量与单条混用时 seq 仍全局单调，无重号（UNIQUE 约束不被打破）。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    assert session_store.append_session_event(sid, {"type": "node_start"}) == 1
    seqs = session_store.append_session_events(
        sid, [{"type": "thinking_token"}, {"type": "thinking_token"}]
    )
    assert seqs == [2, 3]
    assert session_store.append_session_event(sid, {"type": "node_complete"}) == 4

    rows = session_store.list_session_events(sid, after_seq=0)
    assert [r["seq"] for r in rows] == [1, 2, 3, 4]


def test_batch_append_empty_batch(tmp_path, monkeypatch):
    """空批次返回空列表，不触碰数据库。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    assert session_store.append_session_events(sid, []) == []
    assert session_store.list_session_events(sid, after_seq=0) == []


# ── stream_registry.publish_many ──


async def _next_event(gen, timeout=2.0):
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


@pytest.mark.asyncio
async def test_publish_many_journals_then_fans_out_in_order(tmp_path, monkeypatch):
    """publish_many 批量落库后按序 fan-out，事件注入分配的 seq。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def dummy_task():
        await asyncio.sleep(10)

    await reg.start(sid, dummy_task())
    gen = reg.subscribe(sid, after_seq=0)

    seqs = await reg.publish_many(
        sid,
        [
            {"type": "thinking_token", "token": "x"},
            {"type": "thinking_token", "token": "y"},
            {"type": "node_complete", "node_id": "trader"},
        ],
    )
    assert seqs == [1, 2, 3]

    e1 = await _next_event(gen)
    e2 = await _next_event(gen)
    e3 = await _next_event(gen)
    assert (e1["token"], e1["seq"]) == ("x", 1)
    assert (e2["token"], e2["seq"]) == ("y", 2)
    assert (e3["type"], e3["seq"]) == ("node_complete", 3)

    rows = session_store.list_session_events(sid, after_seq=0)
    assert [r["seq"] for r in rows] == [1, 2, 3]
    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_publish_many_dedups_terminal_within_run(tmp_path, monkeypatch):
    """批内/批后重复终态事件被 per-run CAS 丢弃，不落库不 fan-out。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    async def dummy_task():
        await asyncio.sleep(10)

    await reg.start(sid, dummy_task())

    seqs = await reg.publish_many(
        sid,
        [
            {"type": "thinking_token", "token": "t"},
            {"type": "done"},
            {"type": "done"},
        ],
    )
    # 批内第二个 done 被 CAS 过滤
    assert seqs == [1, 2]
    # 批后再发 done 仍被过滤
    assert await reg.publish(sid, {"type": "done"}) == 0

    rows = session_store.list_session_events(sid, after_seq=0)
    assert [json_type(r) for r in rows] == ["thinking_token", "done"]
    await reg.cancel(sid)


def json_type(row) -> str:
    return json.loads(row["event_json"])["type"]


# ── api.py ReAct 循环接线 ──


@pytest.mark.asyncio
async def test_react_loop_batches_thinking_tokens(tmp_path, monkeypatch):
    """_run_react_analysis 的 thinking_token SHALL 走批量落库且 journal 序完整。"""
    import time as time_mod

    import finance_agent.agent_factory as agent_factory
    import finance_agent.api as api_mod

    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    # 批次计数探针：包住 append_session_events（仅 publish_many 使用）
    batch_calls: list[int] = []
    real_batch = session_store.append_session_events

    def counting_batch(session_id, events):
        batch_calls.append(len(events))
        return real_batch(session_id, events)

    monkeypatch.setattr(session_store, "append_session_events", counting_batch)

    async def fake_stream(agent, user_input, **kwargs):
        import json as json_mod

        for i in range(40):
            yield (
                "data: "
                + json_mod.dumps({"type": "thinking_token", "token": f"t{i}"}, ensure_ascii=False)
                + "\n\n"
            )
        yield "data: " + json_mod.dumps({"type": "node_complete", "node_id": "trader"}) + "\n\n"
        yield ": heartbeat\n\n"

    monkeypatch.setattr(agent_factory, "build_agent", lambda **kw: object())
    monkeypatch.setattr(agent_factory, "stream_agent_to_sse", fake_stream)

    req = api_mod.AnalyzeRequest(query="测试批量")
    await api_mod._run_react_analysis(sid, req, "aid", time_mod.time(), None, None)

    # 批量确实发生：40 条 token 至少分 2 批（BATCH_MAX=32），总条数守恒
    assert sum(batch_calls) == 40, f"thinking_token 应全部经批量通道: {batch_calls}"
    assert len(batch_calls) >= 2, f"40 条 token 应合并为多批而非逐条: {batch_calls}"

    # journal 序完整：token 按原顺序、seq 连续（与边界事件交错仍单调）
    rows = session_store.list_session_events(sid, after_seq=0)
    tokens = [
        json.loads(r["event_json"])
        for r in rows
        if json.loads(r["event_json"]).get("type") == "thinking_token"
    ]
    assert [t["token"] for t in tokens] == [f"t{i}" for i in range(40)]
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(seqs), "journal seq 必须单调"
    assert len(set(seqs)) == len(seqs), "seq 不得重号"


# ── PipelineRunner fast path 接线 ──


def _sse(d: dict) -> str:
    import json

    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def test_pipeline_runner_batches_thinking_tokens(tmp_path, monkeypatch):
    """fast path（loop 桥接 journal 模式）的 thinking_token SHALL 批量落库。"""
    import asyncio
    import threading

    from finance_agent.pipeline_runner import PipelineRunner

    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    batch_calls: list[int] = []
    real_batch = session_store.append_session_events

    def counting_batch(session_id, events):
        batch_calls.append(len(events))
        return real_batch(session_id, events)

    monkeypatch.setattr(session_store, "append_session_events", counting_batch)

    def source():
        for i in range(40):
            yield _sse({"type": "thinking_token", "token": f"t{i}", "node": "trader"})
        yield _sse({"type": "node_complete", "node_id": "trader"})

    # 后台事件循环线程：publish/publish_many 经 run_coroutine_threadsafe 桥接
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        PipelineRunner.start(
            sid,
            source,
            {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0},
            loop=loop,
        )
        import time as time_mod

        for _ in range(100):
            if not PipelineRunner.is_running(sid):
                break
            time_mod.sleep(0.1)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=5)

    assert sum(batch_calls) == 40, f"thinking_token 应全部经批量通道: {batch_calls}"
    assert len(batch_calls) >= 2, f"40 条 token 应合并为多批而非逐条: {batch_calls}"

    rows = session_store.list_session_events(sid, after_seq=0)
    types = [json_type(r) for r in rows]
    assert types[-1] == "done", "管线结束后应发布 done 终态"
    tokens = [
        json.loads(r["event_json"])["token"] for r in rows if json_type(r) == "thinking_token"
    ]
    assert tokens == [f"t{i}" for i in range(40)], "token 顺序不得被批量打乱"
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
