"""Check session data for debugging."""

from finance_agent.session_store import get_session, list_sessions

sessions = list_sessions()
print(f"Total sessions: {len(sessions)}")
for s in sessions[:15]:
    detail = get_session(s["session_id"])
    chat_len = len(detail.get("chat_history", [])) if detail else 0
    report_len = len(detail.get("report_markdown", "")) if detail else 0
    stype = s.get("session_type", "?")
    name = s["display_name"][:30]
    print(
        f"  id={s['session_id'][:8]} type={stype} name={name} chat={chat_len} report={report_len}"
    )
