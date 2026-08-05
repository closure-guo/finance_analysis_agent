"""诊断脚本：对比 chat_history 与事件 journal，定位数据丢失层级。

场景：调用 search_stock 工具后切换会话，agent 思考和工具调用内容消失。
诊断目标：
1. chat_history 中 assistant 消息是否包含 thinking/tool_calls
2. session_events journal 中 thinking_token/tool_call 事件是否存在
3. 如果 chat_history 有但前端看不到 -> 前端恢复 bug
4. 如果 chat_history 没有但 journal 有 -> 持久化 bug
5. 如果 journal 也没有 -> 事件发布 bug
"""

import json
import sqlite3
import sys

conn = sqlite3.connect("data/sessions.db")
conn.row_factory = sqlite3.Row

# 查询最近的 clarifying/running 会话（这些是最可能出现问题的）
print("=" * 70)
print("1. 最近的 clarifying/running/interrupted 会话")
print("=" * 70)
cur = conn.execute(
    "SELECT session_id, display_name, status, created_at "
    "FROM sessions WHERE status IN ('clarifying', 'running', 'interrupted') "
    "ORDER BY created_at DESC LIMIT 3"
)
recent_sessions = cur.fetchall()
if not recent_sessions:
    print("无 clarifying/running/interrupted 会话")
    sys.exit(0)

for s in recent_sessions:
    print(f"  {s['session_id']}: {s['display_name']} [{s['status']}]")

# 对最近会话逐一分析
for s in recent_sessions:
    sid = s["session_id"]
    print(f"\n{'=' * 70}")
    print(f"2. 会话 {sid} ({s['display_name']}) 详细分析")
    print("=" * 70)

    # chat_history
    cur2 = conn.execute("SELECT chat_history FROM sessions WHERE session_id = ?", (sid,))
    row = cur2.fetchone()
    history = json.loads(row["chat_history"]) if row and row["chat_history"] else []

    print(f"\nchat_history: {len(history)} 条")
    for i, h in enumerate(history):
        role = h.get("role", "?")
        has_thinking = bool(h.get("thinking"))
        has_tool_calls = bool(h.get("tool_calls"))
        has_timeline = bool(h.get("agentTimeline"))
        content_len = len(h.get("content", "") or "")
        marker = " <-- assistant" if role == "assistant" else ""
        print(
            f"  [{i}] {role}: content={content_len}ch, thinking={has_thinking}, "
            f"tool_calls={has_tool_calls}, agentTimeline={has_timeline}{marker}"
        )

    # 最后一条 assistant 详细内容
    last_assistant = None
    for h in reversed(history):
        if h.get("role") == "assistant":
            last_assistant = h
            break

    if last_assistant:
        print("\n最后一条 assistant 详细:")
        print(f"  content: {last_assistant.get('content', '')[:80]}...")
        thinking = last_assistant.get("thinking")
        print(f"  thinking: {len(str(thinking))}ch" if thinking else "  thinking: 无")
        tcs = last_assistant.get("tool_calls") or []
        print(f"  tool_calls: {len(tcs)} 个")
        for tc in tcs[:3]:
            print(f"    - {tc.get('name', '?')} (result={'有' if tc.get('result') else '无'})")
        at = last_assistant.get("agentTimeline")
        print(f"  agentTimeline: {len(at)} items" if at else "  agentTimeline: 无")
    else:
        print("\n无 assistant 消息")

    # 事件 journal 统计
    cur3 = conn.execute("SELECT COUNT(*) as cnt FROM session_events WHERE session_id = ?", (sid,))
    total_events = cur3.fetchone()["cnt"]
    print(f"\n事件 journal: 共 {total_events} 条")

    # 事件类型统计
    cur4 = conn.execute("SELECT event_json FROM session_events WHERE session_id = ?", (sid,))
    event_types = {}
    for row in cur4.fetchall():
        try:
            ev = json.loads(row["event_json"])
            t = ev.get("type", "?")
            event_types[t] = event_types.get(t, 0) + 1
        except json.JSONDecodeError:
            pass
    print(f"事件类型: {event_types}")

    # 关键判断：chat_history 有 thinking 但前端看不到？
    if last_assistant and last_assistant.get("thinking"):
        print(
            f"\n>>> 结论: chat_history 有 thinking ({len(str(last_assistant.get('thinking')))}ch)，"
            f"如果前端看不到，是前端恢复 bug"
        )
    elif total_events > 0 and event_types.get("thinking_token", 0) > 0:
        print(
            f"\n>>> 结论: journal 有 thinking_token ({event_types.get('thinking_token')}条) "
            f"但 chat_history 无，是持久化 bug"
        )
    elif total_events > 0:
        print("\n>>> 结论: journal 有事件但无 thinking_token，可能事件发布时机问题")

conn.close()
