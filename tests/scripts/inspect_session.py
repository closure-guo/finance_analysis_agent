"""检查指定会话的持久化状态（chat_history / session_events）。"""

import json
import sqlite3
import sys

sessionId = sys.argv[1] if len(sys.argv) > 1 else "2f7ec0cb-c5b"

conn = sqlite3.connect("/app/data/sessions.db")
conn.row_factory = sqlite3.Row

columns = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
idCol = "session_id" if "session_id" in columns else "id"

row = conn.execute(f"SELECT * FROM sessions WHERE {idCol}=?", (sessionId,)).fetchone()
if not row:
    print(f"会话不存在: {sessionId}")
    sys.exit(1)

data = dict(row)
print("status:", data.get("status"), "| type:", data.get("session_type"))
history = json.loads(data.get("chat_history") or "[]")
print(f"chat_history: {len(history)} 条")
for message in history:
    role = message.get("role")
    content = (message.get("content") or "")[:80].replace("\n", " ")
    toolCalls = message.get("tool_calls") or []
    thinkingLen = len(message.get("thinking") or "")
    toolNames = [t.get("name") for t in toolCalls if isinstance(t, dict)]
    hasResult = any(
        isinstance(t, dict) and (t.get("result") or t.get("status") == "done") for t in toolCalls
    )
    print(
        f"  [{role}] tools={toolNames} result={'Y' if hasResult else 'N'} "
        f"thinking={thinkingLen}c | {content}"
    )

try:
    eventCount = conn.execute(
        "SELECT COUNT(*) c FROM session_events WHERE session_id=?", (sessionId,)
    ).fetchone()
    print("session_events:", eventCount["c"])
except sqlite3.OperationalError as e:
    print("session_events 查询失败:", e)
