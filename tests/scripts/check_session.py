"""检查会话状态和事件。"""

import json

from finance_agent import session_store

sessions = session_store.list_sessions()
sid = None
for s in sessions:
    if s["session_id"].startswith("5b88363a"):
        sid = s["session_id"]
        break

if not sid:
    print("Session not found")
    exit(1)

session = session_store.get_session(sid)
print(f"Session: {sid}")
print(f"Status: {session['status']}")
print(f"Type: {session['session_type']}")
history = session.get("chat_history", [])
print(f"chat_history entries: {len(history)}")
for msg in history:
    role = msg.get("role")
    content = str(msg.get("content", ""))[:80]
    print(f"  [{role}] {content}...")

events = session_store.list_session_events(sid)
print(f"\nEvents: {len(events)}")
for e in events:
    event = json.loads(e["event_json"])
    etype = event.get("type")
    token = str(event.get("token", ""))[:30]
    print(f"  seq={e['seq']} type={etype} token={token}")
