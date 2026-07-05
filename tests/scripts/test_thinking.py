"""Test thinking content streaming — follow-up question with session_id."""

import json

import requests

# First, list sessions to get a session_id
resp = requests.get("http://127.0.0.1:8000/api/sessions", timeout=60)
data = resp.json()
sessions = data.get("sessions", data) if isinstance(data, dict) else data
print(
    f"Sessions type: {type(sessions)}, count: {len(sessions) if isinstance(sessions, list) else 'N/A'}"
)
if sessions:
    print(
        f"First session keys: {list(sessions[0].keys()) if isinstance(sessions[0], dict) else sessions[0]}"
    )
    s = sessions[0]
    session_id = s.get("id") or s.get("session_id") or s.get("sessionId") or ""
    if not session_id:
        print(f"Session data: {json.dumps(s, ensure_ascii=False)[:300]}")
        exit(1)
    print(f"Using session: {s.get('stock_name', 'unknown')} ({session_id[:8]}...)")
else:
    print("No sessions found")
    exit(1)

# Send follow-up question
resp = requests.post(
    "http://127.0.0.1:8000/api/chat",
    json={"message": "毛利率为什么这么高？", "session_id": session_id, "api_key": ""},
    stream=True,
    timeout=60,
)

thinking_tokens = 0
answer_tokens = 0
thinking_preview = ""
answer_preview = ""

for line in resp.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        event = json.loads(line[6:])
        etype = event["type"]
        if etype == "thinking_token":
            thinking_tokens += 1
            if len(thinking_preview) < 300:
                thinking_preview += event["token"]
        elif etype == "chat_token":
            answer_tokens += 1
            if len(answer_preview) < 400:
                answer_preview += event["token"]
        elif etype == "chat_done":
            print(f"\nThinking tokens: {thinking_tokens}")
            print(f"Answer tokens: {answer_tokens}")
            print(f"\nThinking preview: {thinking_preview[:300]}...")
            print(f"\nAnswer preview: {answer_preview[:400]}...")
            break
        elif etype == "error":
            print(f"Error: {event.get('message', '')}")
            break
