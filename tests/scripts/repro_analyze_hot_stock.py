"""复现脚本：POST /api/analyze "分析一下热门股票"，不切走连接，观察完整事件流。"""

import json
import time
import urllib.request

req = urllib.request.Request(
    "http://localhost:8000/api/analyze",
    data=json.dumps({"query": "分析一下热门股票"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

startTs = time.monotonic()
eventTypes: list[str] = []
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        buffer = b""
        for chunk in resp:
            buffer += chunk
            while b"\n\n" in buffer:
                rawEvent, buffer = buffer.split(b"\n\n", 1)
                for line in rawEvent.decode("utf-8", errors="replace").splitlines():
                    if line.startswith("data:"):
                        elapsed = time.monotonic() - startTs
                        payload = json.loads(line[5:].strip())
                        eventType = payload.get("type", "?")
                        eventTypes.append(eventType)
                        if eventType != "thinking_token":
                            preview = json.dumps(payload, ensure_ascii=False)[:150]
                            print(f"[{elapsed:6.1f}s] [{eventType}] {preview}", flush=True)
                        if eventType in ("done", "error", "interrupted"):
                            raise SystemExit(0)
except Exception as e:
    elapsed = time.monotonic() - startTs
    print(f"[{elapsed:6.1f}s] 连接结束/异常: {type(e).__name__}: {e}")
    print(f"事件统计: {len(eventTypes)} 个, 序列: {sorted(set(eventTypes))}")
