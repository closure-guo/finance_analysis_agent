"""验证脚本：真实链路测试 /api/chat 快速模式（直连后端 API，属集成验证非 E2E）。

用法：python tests/scripts/verify_quick_chat.py
成功标准：收到 search_start -> tool_result/search_result -> chat_token -> done 完整序列。
"""

import json
import urllib.request

req = urllib.request.Request(
    "http://localhost:8000/api/chat",
    data=json.dumps({"message": "沈阳天气"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

eventTypes: list[str] = []
with urllib.request.urlopen(req, timeout=90) as resp:
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
                    if eventType in (
                        "search_start",
                        "tool_call",
                        "search_result",
                        "tool_result",
                        "session_created",
                        "chat_done",
                        "done",
                        "error",
                    ):
                        preview = json.dumps(payload, ensure_ascii=False)[:160]
                        print(f"[{eventType}] {preview}", flush=True)
                    elif eventType == "chat_token":
                        print(payload.get("token", ""), end="", flush=True)

print()
print("---")
print(f"事件统计: {len(eventTypes)} 个, 类型序列: {sorted(set(eventTypes))}")
assert "tool_call" in eventTypes, "缺少 tool_call"
assert "done" in eventTypes, "缺少 done（流未正常结束）"
assert "error" not in eventTypes, "存在 error 事件"
print("PASS: 快速模式完整链路正常")
