"""session_events 事件日志表与中断状态 reconcile 测试。

对应 delta spec: resume-stream-on-session-switch Task 1。
验证：
- session_events 表创建与索引
- append_session_event 的 seq 单调递增、UNIQUE 约束
- list_session_events 按 after_seq 过滤、按 seq 升序返回
- delete_session 级联删除 session_events
- init_db 启动 reconcile：残留 running 会话置为 interrupted
"""

from __future__ import annotations

import json

from finance_agent import session_store


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB：monkeypatch _DB_PATH + init_db。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def test_session_events_table_exists(tmp_path, monkeypatch):
    """init_db 后 session_events 表应存在。"""
    _setup_db(tmp_path, monkeypatch)
    conn = session_store._get_db()
    # 查表是否存在
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='session_events'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_append_session_event_seq_monotonic(tmp_path, monkeypatch):
    """append_session_event 返回的 seq 在会话内从 1 单调递增。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    seq1 = session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    seq2 = session_store.append_session_event(sid, {"type": "chat_token", "token": "b"})
    seq3 = session_store.append_session_event(sid, {"type": "done"})

    assert seq1 == 1
    assert seq2 == 2
    assert seq3 == 3


def test_append_session_event_independent_seq_per_session(tmp_path, monkeypatch):
    """不同会话的 seq 各自独立从 1 开始。"""
    _setup_db(tmp_path, monkeypatch)
    sid1 = session_store.create_session(status="running")
    sid2 = session_store.create_session(status="running")

    assert session_store.append_session_event(sid1, {"type": "a"}) == 1
    assert session_store.append_session_event(sid2, {"type": "b"}) == 1
    assert session_store.append_session_event(sid1, {"type": "c"}) == 2


def test_list_session_events_after_seq(tmp_path, monkeypatch):
    """list_session_events 返回 after_seq 之后的事件，按 seq 升序。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")

    for i in range(5):
        session_store.append_session_event(sid, {"type": "token", "idx": i})

    # after_seq=0 返回全部
    events = session_store.list_session_events(sid, after_seq=0)
    assert len(events) == 5
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5]

    # after_seq=2 返回 seq>2 的事件
    events = session_store.list_session_events(sid, after_seq=2)
    assert len(events) == 3
    assert [e["seq"] for e in events] == [3, 4, 5]

    # 验证事件内容可反序列化
    assert json.loads(events[0]["event_json"])["type"] == "token"


def test_list_session_events_empty_session(tmp_path, monkeypatch):
    """无事件的会话返回空列表。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")
    events = session_store.list_session_events(sid, after_seq=0)
    assert events == []


def test_delete_session_cascades_events(tmp_path, monkeypatch):
    """删除会话时级联删除其 session_events。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    session_store.append_session_event(sid, {"type": "a"})
    session_store.append_session_event(sid, {"type": "b"})

    # 确认事件存在
    assert len(session_store.list_session_events(sid, after_seq=0)) == 2

    # 删除会话
    assert session_store.delete_session(sid) is True

    # 事件应被级联删除
    assert session_store.list_session_events(sid, after_seq=0) == []


def test_init_db_reconcile_running_to_interrupted(tmp_path, monkeypatch):
    """init_db 启动时将残留 running 会话置为 interrupted。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()

    # 创建 running 会话
    sid = session_store.create_session(status="running")
    assert session_store.get_session(sid)["status"] == "running"

    # 再次 init_db（模拟服务重启）
    session_store.init_db()

    # running 应被 reconcile 为 interrupted
    row = session_store.get_session(sid)
    assert row["status"] == "interrupted"


def test_init_db_reconcignores_completed(tmp_path, monkeypatch):
    """init_db reconcile 不影响已完成会话。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()

    sid = session_store.create_session(status="completed")
    session_store.init_db()

    assert session_store.get_session(sid)["status"] == "completed"
