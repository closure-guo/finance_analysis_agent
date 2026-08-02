"""检查 journal 事件的 created_at 时间戳，确认任务实际执行时长。"""

import asyncio
import json
import os
import sqlite3
import tempfile
import time
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
        requestStart = time.monotonic()
        async with client.stream("POST", "/api/chat", json={"message": "茅台最新消息"}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    break
        streamCloseTime = time.monotonic()

        sid = session_store.list_sessions()[0]["session_id"]

        # 轮询等任务完成
        for i in range(100):
            await asyncio.sleep(0.1)
            if not registry.is_active(sid):
                doneTime = time.monotonic()
                print(
                    f"stream closed at {streamCloseTime - requestStart:.2f}s, "
                    f"task done at {doneTime - requestStart:.2f}s",
                    flush=True,
                )
                break
        else:
            print("task still active after 10s", flush=True)

        # 查 created_at
        conn = sqlite3.connect(str(session_store._DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT seq, created_at, event_json FROM session_events WHERE session_id=? ORDER BY seq",
            (sid,),
        ).fetchall()
        for row in rows:
            ev = json.loads(row["event_json"])
            print(
                f"seq={row['seq']} created_at={row['created_at']} type={ev.get('type')}", flush=True
            )
        conn.close()


asyncio.run(main())
