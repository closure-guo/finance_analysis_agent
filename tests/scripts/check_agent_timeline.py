"""检查 0e3db0b2-44f 会话 agentTimeline 的实际内容。"""

import json
import sqlite3

conn = sqlite3.connect("data/sessions.db")
conn.row_factory = sqlite3.Row
cur = conn.execute("SELECT chat_history FROM sessions WHERE session_id = '0e3db0b2-44f'")
row = cur.fetchone()
history = json.loads(row["chat_history"]) if row and row["chat_history"] else []

for i, h in enumerate(history):
    if h.get("role") == "assistant":
        print(f"=== assistant 消息 [{i}] ===")
        print(f"content: {h.get('content', '')[:100]}...")
        print(f"\nthinking ({len(h.get('thinking', '') or '')}ch):")
        print(h.get("thinking", "")[:200])
        print(f"\ntool_calls ({len(h.get('tool_calls') or [])} 个):")
        for tc in h.get("tool_calls") or []:
            print(
                f"  - name={tc.get('name')}, args={tc.get('args')}, "
                f"result_text_len={len(tc.get('result_text', '') or '')}"
            )
        print(f"\nagentTimeline ({len(h.get('agentTimeline') or [])} items):")
        for j, item in enumerate(h.get("agentTimeline") or []):
            print(
                f"  [{j}] type={item.get('type')}, name={item.get('name', '-')}, "
                f"content_len={len(item.get('content', '') or '')}"
            )
conn.close()
