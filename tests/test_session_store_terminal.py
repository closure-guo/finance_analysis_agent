"""session_store 终态事件查询函数测试。"""

from finance_agent import session_store


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def test_has_terminal_event_true_when_done_exists(tmp_path, monkeypatch):
    """journal 中有 done 事件时，has_terminal_event 返回 True。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    session_store.append_session_event(sid, {"type": "done"})
    assert session_store.has_terminal_event(sid) is True


def test_has_terminal_event_true_when_interrupted_exists(tmp_path, monkeypatch):
    """journal 中有 interrupted 事件时，has_terminal_event 返回 True。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "interrupted"})
    assert session_store.has_terminal_event(sid) is True


def test_has_terminal_event_true_when_error_exists(tmp_path, monkeypatch):
    """journal 中有 error 事件时，has_terminal_event 返回 True。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "error", "message": "test"})
    assert session_store.has_terminal_event(sid) is True


def test_has_terminal_event_false_when_no_terminal(tmp_path, monkeypatch):
    """journal 中只有非终态事件时，has_terminal_event 返回 False。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    session_store.append_session_event(sid, {"type": "chat_token", "token": "b"})
    assert session_store.has_terminal_event(sid) is False


def test_has_terminal_event_false_when_no_events(tmp_path, monkeypatch):
    """无事件时，has_terminal_event 返回 False。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    assert session_store.has_terminal_event(sid) is False


def test_get_terminal_event_returns_last_terminal(tmp_path, monkeypatch):
    """get_terminal_event 返回最后一条终态事件。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    session_store.append_session_event(sid, {"type": "done"})
    result = session_store.get_terminal_event(sid)
    assert result is not None
    assert result["type"] == "done"
    assert "seq" in result


def test_get_terminal_event_returns_none_when_no_terminal(tmp_path, monkeypatch):
    """无终态事件时，get_terminal_event 返回 None。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    assert session_store.get_terminal_event(sid) is None


def test_get_terminal_event_returns_none_when_no_events(tmp_path, monkeypatch):
    """无事件时，get_terminal_event 返回 None。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    assert session_store.get_terminal_event(sid) is None
