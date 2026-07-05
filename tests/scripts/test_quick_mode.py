"""Quick test for /api/chat endpoint — verifies streaming + search events."""

import json

import requests

resp = requests.post(
    "http://127.0.0.1:8000/api/chat",
    json={"message": "茅台", "api_key": ""},
    stream=True,
    timeout=60,
)

events = []
for line in resp.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        event = json.loads(line[6:])
        etype = event["type"]
        if etype == "chat_token":
            print(event["token"], end="", flush=True)
        elif etype == "chat_done":
            print("\n\n[done]")
        elif etype == "search_start":
            print(f"\n[search_start] query={event['query']}")
        elif etype == "search_result":
            print(f"[search_result] count={event['count']}")
        elif etype == "search_error":
            print(f"[search_error] {event['message']}")
        elif etype == "error":
            print(f"[error] {event.get('message', '')}")
        events.append(etype)

print(f"\n\nEvent sequence: {events}")
