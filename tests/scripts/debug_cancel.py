"""调试 cancel 行为：检查 registry 状态与 cancel 响应。"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["TESTING"] = "1"
os.environ["STUB_SCENARIO"] = "tool_call"

from finance_agent import session_store

session_store._DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
session_store.init_db()

import finance_agent.api as apiModule

apiModule.TESTING = True
import httpx

from finance_agent.api import app, registry


async def main():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with client.stream("POST", "/api/chat", json={"message": "茅台最新消息"}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    break

        sid = session_store.list_sessions()[0]["session_id"]
        print(f"session: {sid}", flush=True)

        # 检查 TESTING 值与工具注册
        from finance_agent.api import TESTING as _t

        print(f"api.TESTING={_t}", flush=True)
        from finance_agent.agent_factory import build_agent

        agent = build_agent(mode="quick")
        func = agent.tools.tools.get("web_search")
        print(f"web_search func={func.__name__ if func else None}", flush=True)

        # 立即检查 registry 状态（不等 1s）
        print(f"registry.is_active(0s): {registry.is_active(sid)}", flush=True)
        stream = registry._streams.get(sid)
        if stream and stream.task:
            t = stream.task
            print(f"task done={t.done()} cancelled={t.cancelled()} at 0s", flush=True)
        await asyncio.sleep(0.05)
        stream = registry._streams.get(sid)
        if stream and stream.task:
            t = stream.task
            print(f"task done={t.done()} cancelled={t.cancelled()} at 0.05s", flush=True)
            if t.done() and not t.cancelled():
                print(f"task exception={t.exception()}", flush=True)
        else:
            print("stream gone at 0.05s", flush=True)
        await asyncio.sleep(0.05)
        print(f"registry.is_active(0.1s): {registry.is_active(sid)}", flush=True)
        await asyncio.sleep(0.5)
        print(f"registry.is_active(0.6s): {registry.is_active(sid)}", flush=True)

        session = session_store.get_session(sid)
        history = session["chat_history"]
        print(f"history len={len(history)}", flush=True)
        for m in history:
            role = m.get("role")
            tools = m.get("tool_calls") or []
            toolNames = [t.get("name") for t in tools if isinstance(t, dict)]
            content = (m.get("content") or "")[:80]
            print(f"  [{role}] tools={toolNames} | {content}", flush=True)
        events = session_store.list_session_events(sid, 0)
        print(f"journal events: {len(events)}", flush=True)
        for row in events:
            ev = json.loads(row["event_json"])
            etype = ev.get("type")
            preview = json.dumps(ev, ensure_ascii=False)[:120]
            print(f"  seq={row['seq']} {preview}", flush=True)

        resp = await client.post(f"/api/sessions/{sid}/cancel")
        print(f"cancel status={resp.status_code} body={resp.json()}", flush=True)

        for _ in range(50):
            events = session_store.list_session_events(sid, 0)
            for row in events:
                ev = json.loads(row["event_json"])
                if ev.get("type") in ("done", "interrupted", "error"):
                    print(f"terminal: {ev}", flush=True)
                    session = session_store.get_session(sid)
                    print(f"session status: {session['status']}", flush=True)
                    return
            await asyncio.sleep(0.2)
        print("NO TERMINAL", flush=True)


asyncio.run(main())
