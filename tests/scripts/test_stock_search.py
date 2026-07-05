"""Test quick mode with stock question to verify Tavily works."""

import json

import requests

resp = requests.post(
    "http://127.0.0.1:8000/api/chat",
    json={
        "message": "茅台最新财报",
        "api_key": "",
    },
    stream=True,
    timeout=60,
)

events = []
for line in resp.iter_lines():
    if not line:
        continue
    line = line.decode()
    if line.startswith("data: "):
        event = json.loads(line[6:])
        events.append(event["type"])
        if event["type"] == "search_start":
            print(f"[search_start] query={event['query']}")
        elif event["type"] == "search_result":
            print(f"[search_result] count={len(event.get('results', []))}")
        elif event["type"] == "search_error":
            print(f"[search_error] {event.get('message', '')}")
        elif event["type"] == "chat_done":
            break

print(f"\nEvent sequence: {events}")
