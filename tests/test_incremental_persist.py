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
