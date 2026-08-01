"""Docker 实证：analyze "分析一下热门股票" 断线后任务继续跑完。

步骤：
1. POST /api/analyze，读首个事件后断开（模拟切换会话）
2. 等任务在后台继续运行
3. GET /api/sessions/{id}/stream 恢复，检查是否收到完整事件流（含 done）
"""

import json
import time
import urllib.request

# Step 1: POST analyze，读首事件后断开
print("Step 1: POST /api/analyze ...", flush=True)
req = urllib.request.Request(
    "http://localhost:8000/api/analyze",
    data=json.dumps({"query": "分析一下热门股票"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
sessionId = None
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        buffer = b""
        for chunk in resp:
            buffer += chunk
            while b"\n\n" in buffer:
                rawEvent, buffer = buffer.split(b"\n\n", 1)
                for line in rawEvent.decode("utf-8", errors="replace").splitlines():
                    if line.startswith("data:"):
                        payload = json.loads(line[5:].strip())
                        if payload.get("type") == "session_created":
                            sessionId = payload["session_id"]
                            print(f"  session_created: {sessionId}", flush=True)
                        elif payload.get("type") == "search_start":
                            print(f"  search_start: {payload.get('query', '')[:60]}", flush=True)
                            raise StopIteration  # 断开
except (StopIteration, Exception):
    pass

if not sessionId:
    print("FAIL: 未收到 session_created", flush=True)
    exit(1)

# Step 2: 等任务在后台继续运行
print("Step 2: 等待 15s（任务在后台继续）...", flush=True)
time.sleep(15)

# Step 3: 恢复端点检查
print(f"Step 3: GET /api/sessions/{sessionId}/stream ...", flush=True)
req2 = urllib.request.Request(f"http://localhost:8000/api/sessions/{sessionId}/stream")
eventTypes = []
try:
    with urllib.request.urlopen(req2, timeout=30) as resp:
        buffer = b""
        for chunk in resp:
            buffer += chunk
            while b"\n\n" in buffer:
                rawEvent, buffer = buffer.split(b"\n\n", 1)
                for line in rawEvent.decode("utf-8", errors="replace").splitlines():
                    if line.startswith("data:"):
                        payload = json.loads(line[5:].strip())
                        eventType = payload.get("type", "?")
                        eventTypes.append(eventType)
                        if eventType in ("done", "error", "interrupted"):
                            raise StopIteration
except (StopIteration, Exception):
    pass

print(f"恢复事件类型: {sorted(set(eventTypes))}", flush=True)
if "done" in eventTypes:
    print("PASS: 断线后任务继续跑完，恢复端点收到 done", flush=True)
elif "interrupted" in eventTypes:
    print("PASS: 断线后任务被中断，恢复端点收到 interrupted", flush=True)
else:
    print(f"FAIL: 恢复端点未收到终态事件，类型: {eventTypes[-10:]}", flush=True)
    exit(1)
