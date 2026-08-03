"""增量持久化测试：upsert_chat 对已有 assistant 消息做更新，对无 assistant 消息做追加。"""

from finance_agent import session_store


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def test_upsert_chat_updates_existing_assistant(tmp_path, monkeypatch):
    """已有 assistant 消息时，upsert_chat 更新而非追加。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_chat(sid, "user", "你好")
    session_store.append_chat(sid, "assistant", "部分回复")

    session_store.upsert_chat(
        sid, "assistant", "完整回复", thinking="思考过程", tool_calls=[{"name": "web_search"}]
    )

    session = session_store.get_session(sid)
    history = session["chat_history"]
    assert len(history) == 2
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "完整回复"
    assert history[1]["thinking"] == "思考过程"
    assert len(history[1]["tool_calls"]) == 1


def test_upsert_chat_appends_when_no_assistant(tmp_path, monkeypatch):
    """无 assistant 消息时，upsert_chat 追加新消息。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_chat(sid, "user", "你好")

    session_store.upsert_chat(sid, "assistant", "回复")

    session = session_store.get_session(sid)
    history = session["chat_history"]
    assert len(history) == 2
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "回复"


def test_upsert_chat_appends_when_empty_history(tmp_path, monkeypatch):
    """空 chat_history 时，upsert_chat 追加新消息。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    session_store.upsert_chat(sid, "assistant", "回复")

    session = session_store.get_session(sid)
    history = session["chat_history"]
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "回复"


def test_upsert_chat_updates_last_assistant_only(tmp_path, monkeypatch):
    """多条 assistant 消息时，只更新最后一条。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_chat(sid, "user", "问题1")
    session_store.append_chat(sid, "assistant", "回复1")
    session_store.append_chat(sid, "user", "问题2")
    session_store.append_chat(sid, "assistant", "回复2")

    session_store.upsert_chat(sid, "assistant", "更新回复2")

    session = session_store.get_session(sid)
    history = session["chat_history"]
    assert len(history) == 4
    assert history[1]["content"] == "回复1"
    assert history[3]["content"] == "更新回复2"


def test_upsert_chat_appends_for_new_round_after_user_message(tmp_path, monkeypatch):
    """Bug 复现：新一轮（user 消息已落库、assistant 尚未产生）的增量持久化
    应追加新 assistant 条目，而不是覆盖上一轮的 assistant 内容。

    场景（用户反馈：快速模式追问后切换会话，历史重建中本轮内容串到上一轮位置、
    上一轮内容消失）：
    1. 第一轮：user 沈阳天气 → assistant 沈阳回复（含 agentTimeline）
    2. 第二轮：user 上海天气 落库后，_upsert_assistant_chat 每 10s upsert
       → 修复前会覆盖第一轮 assistant，chat_history 变为
         [user沈阳, assistant上海内容, user上海]，重建后表现为串台+内容丢失
    """
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_chat_session("天气问答")
    # 第一轮完整落库
    session_store.append_chat(sid, "user", "沈阳天气")
    session_store.upsert_chat(
        sid,
        "assistant",
        "沈阳晴",
        thinking="第一轮思考",
        agent_timeline=[{"type": "thinking", "text": "第一轮思考", "done": True}],
    )
    # 第二轮：user 消息落库（assistant 尚未产生）
    session_store.append_chat(sid, "user", "上海天气")

    # 第二轮的首次增量持久化：应追加新 assistant 条目
    session_store.upsert_chat(
        sid,
        "assistant",
        "上海多云",
        thinking="第二轮思考",
        agent_timeline=[{"type": "thinking", "text": "第二轮思考", "done": True}],
    )

    session = session_store.get_session(sid)
    history = session["chat_history"]
    assert len(history) == 4, (
        f"应为 4 条（两轮 user+assistant），实际: {[h['role'] for h in history]}"
    )
    # 第一轮内容不被覆盖
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "沈阳晴"
    assert history[1]["thinking"] == "第一轮思考"
    # 第二轮内容追加在第二轮 user 之后
    assert history[2]["role"] == "user"
    assert history[3]["role"] == "assistant"
    assert history[3]["content"] == "上海多云"
    assert history[3]["thinking"] == "第二轮思考"
