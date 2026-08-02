import json
import sqlite3

conn = sqlite3.connect("data/sessions.db")
conn.row_factory = sqlite3.Row

# 检查分析比亚迪会话的事件
rows = conn.execute(
    "SELECT seq, event_json FROM session_events WHERE session_id = ? ORDER BY seq DESC LIMIT 10",
    ("0d1c0d60-855",),
).fetchall()

print(f"Session events for 0d1c0d60-855: {len(rows)} events")
for r in rows:
    event = json.loads(r["event_json"])
    print(f"  seq={r['seq']}, type={event.get('type')}")
    if event.get("type") == "thinking":
        print(f"    thinking: {str(event.get('content', ''))[:80]}")
    elif event.get("type") == "chat_token":
        print(f"    token: {str(event.get('token', ''))[:50]}")

# 也检查 chat_history
session = conn.execute(
    "SELECT chat_history FROM sessions WHERE session_id = ?", ("0d1c0d60-855",)
).fetchone()
if session:
    history = json.loads(session["chat_history"])
    print(f"\nchat_history: {len(history)} messages")
    for msg in history:
        print(f"  role={msg.get('role')}, content={str(msg.get('content', ''))[:80]}")
        if msg.get("thinking"):
            print(f"    thinking: {str(msg.get('thinking', ''))[:80]}")

conn.close()
