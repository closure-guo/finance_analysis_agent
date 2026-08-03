"""ReAct 路径（/api/chat、/api/analyze）可恢复流测试。

复现真实 bug：快速模式问"分析一下热门股票"后切换会话，SSE 断连杀死生成任务，
journal 无事件（恢复端点 204），chat_history 留悬空 user 消息（无 assistant 回复）。

用 httpx.AsyncClient 保持事件循环持续运行，使 registry 后台任务在请求间不被清理。
对应 spec: resume-stream-on-session-switch
- Decoupled Generation Lifecycle（客户端断开 SHALL NOT 终止生成任务）
- Stream Event Journal（事件落库为重放事实源）
- Graceful Interruption Persistence（中断兜底，无悬空 user 消息）
- Session Single-Flight（运行中拒绝新消息返回 409）
"""

import asyncio
import contextlib
import json
import time

import httpx
import pytest

import finance_agent.api as _api_module
from finance_agent import session_store


@pytest.fixture(autouse=True)
def _restore_testing():
    """每个测试后恢复 api.TESTING 原值，避免跨测试污染。"""
    original = _api_module.TESTING
    yield
    _api_module.TESTING = original


def _setup(tmp_path, monkeypatch, scenario: str | None = None):
    """隔离 DB + 启用 stub LLM（TESTING=1）+ 清理 registry 残留。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    import finance_agent.api as api_module

    monkeypatch.setattr(api_module, "TESTING", True)
    if scenario:
        monkeypatch.setenv("STUB_SCENARIO", scenario)
    else:
        monkeypatch.delenv("STUB_SCENARIO", raising=False)

    # 清理 registry 全局单例残留（避免跨测试污染）
    from finance_agent.stream_registry import registry

    for sid in list(registry._streams.keys()):
        stream = registry._streams[sid]
        if stream.task and not stream.task.done():
            stream.task.cancel()
        registry._streams.pop(sid, None)


def _latest_session_id() -> str:
    sessions = session_store.list_sessions()
    assert sessions, "会话未创建"
    return sessions[0]["session_id"]


async def _wait_terminal_event(session_id: str, timeout: float = 15.0) -> dict:
    """轮询 journal 直到出现终态事件（done/interrupted/error），返回该事件。

    用 asyncio.sleep 不阻塞事件循环，使 registry 后台任务能持续推进。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = session_store.list_session_events(session_id, 0)
        for row in events:
            event = json.loads(row["event_json"])
            if event.get("type") in ("done", "interrupted", "error"):
                return event
        await asyncio.sleep(0.2)
    raise AssertionError(f"超时 {timeout}s 内 journal 无终态事件（任务可能已随连接死亡）")


async def _read_first_event_then_disconnect(
    client: httpx.AsyncClient, url: str, payload: dict
) -> None:
    """POST 流式请求，读到第一个 data 事件后立即断开（模拟切换会话 abort）。"""
    async with client.stream("POST", url, json=payload) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                return
    raise AssertionError("未收到任何 SSE 事件")


async def _consume_stream_until_done(client: httpx.AsyncClient, url: str, payload: dict) -> None:
    """POST 流式请求，消费所有事件直到流结束（用于后台 task 保持连接活跃）。"""
    async with client.stream("POST", url, json=payload) as resp:
        async for _ in resp.aiter_lines():
            pass


@pytest.mark.asyncio
async def test_chat_disconnect_task_continues(tmp_path, monkeypatch):
    """断线不杀任务：/api/chat 收到首事件后断开，任务必须继续跑完并落 journal。

    旧实现：生成器绑在 HTTP 连接上，断开即 CancelledError 杀任务，
    journal 无事件、chat_history 悬空 user 消息--本测试失败。
    """
    _setup(tmp_path, monkeypatch)
    from finance_agent.api import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await _read_first_event_then_disconnect(client, "/api/chat", {"message": "你好"})

    sessionId = _latest_session_id()
    terminal = await _wait_terminal_event(sessionId)
    assert terminal["type"] == "done", f"任务未正常完成: {terminal}"

    # 无悬空 user 消息：最后一条必须是 assistant 回复（stub 固定文本）
    session = session_store.get_session(sessionId)
    history = session["chat_history"]
    assert history[-1]["role"] == "assistant", "chat_history 存在悬空 user 消息"
    assert "测试" in history[-1]["content"]
    # status 正常流转，不残留 running
    assert session["status"] != "running"


@pytest.mark.asyncio
async def test_chat_single_flight_rejects_second_request(tmp_path, monkeypatch):
    """single-flight：任务运行中（stub 搜索 5s 窗口）再发消息返回 409，且不追加 user 消息。

    首个请求用后台 task 发起并持续消费（不 await 完成），确保断言第二个请求时
    首个任务确实仍在运行；若改用"读首事件即断开"，首事件要等 stub sleep 5s 后才到达，
    此时任务已跑完，断言落在任务注销的竞态窗口上（见 fix-terminal-event-dedup-scope）。
    """
    _setup(tmp_path, monkeypatch, scenario="tool_call")
    from finance_agent.api import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 后台发起首个请求并持续消费（任务在 _stub_web_search sleep 5s 窗口内运行）
        streamTask = asyncio.create_task(
            _consume_stream_until_done(client, "/api/chat", {"message": "茅台最新消息"})
        )
        # 等任务启动并进入 sleep 5s 窗口
        await asyncio.sleep(1.0)
        sessionId = _latest_session_id()

        # 任务仍在运行（stub web_search 5s 窗口），第二个请求必须被拒
        resp = await client.post("/api/chat", json={"message": "再问一句", "session_id": sessionId})
        assert resp.status_code == 409, f"运行中未拒绝新消息: {resp.status_code}"
        assert resp.json().get("error") == "session_busy"

        # 等首个任务自然跑完（保持连接活跃，使后台任务能推进）
        await asyncio.wait_for(streamTask, timeout=15.0)

    # 校验 user 消息只有一条（409 未追加）
    terminal = await _wait_terminal_event(sessionId)
    assert terminal["type"] == "done", f"首个任务应正常完成: {terminal}"
    session = session_store.get_session(sessionId)
    userMessages = [m for m in session["chat_history"] if m["role"] == "user"]
    assert len(userMessages) == 1, "409 拒绝时 user 消息被追加"


@pytest.mark.asyncio
async def test_chat_cancel_persists_interrupted(tmp_path, monkeypatch):
    """中断兜底：cancel 后部分回复落库、status=interrupted、journal 有 interrupted 终态。

    用后台 task 发起 stream 请求（不 await 完成），在任务运行中
    （_stub_web_search sleep 5s 窗口）直接发 cancel 请求。
    """
    _setup(tmp_path, monkeypatch, scenario="tool_call")
    from finance_agent.api import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 后台发起 stream 请求（不 await，使其在后台消费事件）
        streamTask = asyncio.create_task(
            _consume_stream_until_done(client, "/api/chat", {"message": "茅台最新消息"})
        )
        # 等任务启动并进入 _stub_web_search sleep 5s 窗口
        await asyncio.sleep(1.0)
        sessionId = _latest_session_id()

        # 任务仍在 sleep 5s 中，发 cancel
        resp = await client.post(f"/api/sessions/{sessionId}/cancel")
        assert resp.status_code == 200, f"cancel 失败: {resp.status_code} {resp.text}"
        streamTask.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await streamTask

    terminal = await _wait_terminal_event(sessionId)
    assert terminal["type"] == "interrupted", f"终态应为 interrupted: {terminal}"

    session = session_store.get_session(sessionId)
    assert session["status"] == "interrupted"
    # 无悬空 user 消息：中断时 collector 已收集 thinking/tool_call，部分回复落库并标注中断
    history = session["chat_history"]
    assert history[-1]["role"] == "assistant", "中断后存在悬空 user 消息"
    assert "中断" in (history[-1].get("content") or "") or history[-1].get("thinking")


@pytest.mark.asyncio
async def test_analyze_disconnect_task_continues(tmp_path, monkeypatch):
    """断线不杀任务（analyze ReAct 路径）：断开后任务跑完，journal 含 awaiting_input + done。"""
    _setup(tmp_path, monkeypatch, scenario="tool_call")
    from finance_agent.api import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 无股票代码 -> ReAct 路径；无时效关键词 -> 跳过预搜索分支（确定性）
        await _read_first_event_then_disconnect(client, "/api/analyze", {"query": "茅台最新消息"})

    sessionId = _latest_session_id()
    terminal = await _wait_terminal_event(sessionId)
    assert terminal["type"] == "done", f"任务未正常完成: {terminal}"

    # ReAct 澄清路径完成：journal 应含 awaiting_input，status 回 clarifying
    events = [
        json.loads(row["event_json"]) for row in session_store.list_session_events(sessionId, 0)
    ]
    eventTypes = [e.get("type") for e in events]
    assert "awaiting_input" in eventTypes, f"journal 缺 awaiting_input: {eventTypes}"

    session = session_store.get_session(sessionId)
    history = session["chat_history"]
    assert history[-1]["role"] == "assistant", "chat_history 存在悬空 user 消息"
    assert session["status"] == "clarifying"
