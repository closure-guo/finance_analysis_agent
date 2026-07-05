"""Test quick mode with non-stock question."""

import json

import requests

resp = requests.post(
    "http://127.0.0.1:8000/api/chat",
    json={"message": "明天天气怎么样", "api_key": ""},
    stream=True,
    timeout=60,
)

events = []
for line in resp.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        event = json.loads(line[6:])
        etype = event["type"]
        events.append(etype)
        if etype == "thinking_token":
            print(f"[thinking] {event['token']}", end="", flush=True)
        elif etype == "chat_token":
            print(event["token"], end="", flush=True)
        elif etype == "search_start":
            print(f"\n[search_start] query={event['query']}")
        elif etype == "search_result":
            print(f"[search_result] count={event['count']}")
        elif etype == "search_error":
            print(f"\n[search_error] {event['message']}")
        elif etype == "error":
            print(f"\n[ERROR] {event.get('message', '')}")
        elif etype == "chat_done":
            print("\n\n[done]")

print(f"\nEvent sequence: {events}")
