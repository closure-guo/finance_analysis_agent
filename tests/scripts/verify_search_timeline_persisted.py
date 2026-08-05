"""验证修复：触发时效性查询，检查 agentTimeline 是否包含 search item。"""

import json
import sqlite3
import time
import urllib.request

# 触发时效性查询（"热门股票"是时效性关键词，会触发预搜索）
payload = json.dumps(
    {
        "query": "分析热门股票",
        "api_key": "test-key",
        "analysis_type": "comprehensive",
    }
).encode()

req = urllib.request.Request(
    "http://localhost:8000/api/analyze",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

print("触发时效性查询（分析热门股票）...")
start_time = time.time()
session_id = None

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            line_str = line.decode("utf-8", errors="ignore").strip()
            if not line_str.startswith("data: "):
                continue
            try:
                ev = json.loads(line_str[6:])
            except json.JSONDecodeError:
                continue
            ev_type = ev.get("type", "")
            if ev_type == "session_created":
                session_id = ev.get("session_id")
                print(f"[{time.time() - start_time:.1f}s] session_created: {session_id}")
            elif ev_type == "search_start":
                print(f"[{time.time() - start_time:.1f}s] search_start: {ev.get('query', '')[:50]}")
            elif ev_type == "search_result":
                print(
                    f"[{time.time() - start_time:.1f}s] search_result: {ev.get('count', 0)} results"
                )
            elif ev_type == "thinking_token":
                pass  # 太多，不打印
            elif ev_type == "tool_call":
                print(f"[{time.time() - start_time:.1f}s] tool_call: {ev.get('name')}")
            elif ev_type == "chat_token":
                pass
            elif ev_type == "awaiting_input":
                print(f"[{time.time() - start_time:.1f}s] awaiting_input（agent 等待用户输入）")
                break
            elif ev_type in ("done", "error", "interrupted"):
                print(f"[{time.time() - start_time:.1f}s] {ev_type}")
                break
except Exception as e:
    print(f"请求异常: {e}")

elapsed = time.time() - start_time
print(f"\n总耗时: {elapsed:.1f}s")

if not session_id:
    print("未获取 session_id，无法检查 agentTimeline")
    exit(1)

# 等待一下让持久化完成
time.sleep(2)

# 检查 agentTimeline
print(f"\n{'=' * 60}")
print(f"检查会话 {session_id} 的 agentTimeline")
print("=" * 60)

conn = sqlite3.connect("data/sessions.db")
conn.row_factory = sqlite3.Row
cur = conn.execute("SELECT chat_history FROM sessions WHERE session_id = ?", (session_id,))
row = cur.fetchone()
if not row or not row["chat_history"]:
    print("chat_history 为空")
    exit(1)

history = json.loads(row["chat_history"])
print(f"chat_history: {len(history)} 条")

for i, h in enumerate(history):
    role = h.get("role", "?")
    at = h.get("agentTimeline") or []
    tcs = h.get("tool_calls") or []
    print(f"  [{i}] {role}: agentTimeline={len(at)} items, tool_calls={len(tcs)} 个")
    if role == "assistant" and at:
        for j, item in enumerate(at):
            t = item.get("type", "?")
            if t == "search":
                print(
                    f"      [{j}] search: status={item.get('status')}, "
                    f"results={len(item.get('results', []))}"
                )
            elif t == "thinking":
                print(f"      [{j}] thinking: {len(item.get('content', ''))}ch")
            elif t == "tool_call":
                print(f"      [{j}] tool_call: {item.get('name')}")

# 关键断言
last_assistant = None
for h in reversed(history):
    if h.get("role") == "assistant":
        last_assistant = h
        break

if last_assistant:
    at = last_assistant.get("agentTimeline") or []
    search_items = [item for item in at if item.get("type") == "search"]
    if search_items:
        print(f"\n>>> PASS: agentTimeline 包含 {len(search_items)} 个 search item")
    else:
        print(f"\n>>> FAIL: agentTimeline 缺少 search item（只有 {[i.get('type') for i in at]}）")

conn.close()
