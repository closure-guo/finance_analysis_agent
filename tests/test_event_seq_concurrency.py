"""复现：append_session_event 的 seq 分配非原子，并发时事件丢失。

根因：`SELECT MAX(seq)` + `INSERT` 两步非原子（session_store.py:281-296）。
并发调用时多个 writer 读到同一个 max_seq，各自算出相同的 nextSeq，
其中一个 INSERT 成功，其余因 UNIQUE (session_id, seq) 约束失败 —— 事件永久丢失。

症状（用户实测）：流式 thinking/chat 文本随机缺整个 token（如「中环海陆（301040）」
变「中陆301040」、「根据最新行情」变「行情当前标:」），概率性出现；
刷新后走 chat_history 落库文本恢复正常（chat_history 是另一条写路径）。

修复标准：并发 append_session_event SHALL 全部成功且 seq 唯一连续，不丢事件。
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from finance_agent import session_store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    return tmp_path / "t.db"


def test_concurrent_append_does_not_lose_events(isolated_db):
    """并发追加事件时，SHALL 全部落库且 seq 唯一（不因 UNIQUE 冲突丢事件）。"""
    sid = session_store.create_session(stock_code="600449", stock_name="宁夏建材", status="running")

    total = 60
    tokens = [f"token-{i}" for i in range(total)]
    errors: list[BaseException] = []

    def append(tok: str) -> None:
        try:
            session_store.append_session_event(sid, {"type": "chat_token", "token": tok})
        except BaseException as e:  # noqa: BLE001 - 复现用，需捕获 UNIQUE 冲突
            errors.append(e)

    # 多线程并发写（模拟流式 token 高频落库 + 管线并发事件）
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(append, tokens))

    events = session_store.list_session_events(sid, after_seq=0)

    assert not errors, (
        f"并发写抛出 {len(errors)} 个异常（首个：{type(errors[0]).__name__}: {errors[0]}）"
    )
    assert len(events) == total, f"事件丢失：期望 {total} 条，实际落库 {len(events)} 条"

    seqs = [e["seq"] for e in events]
    assert len(set(seqs)) == total, "seq 出现重复"
    assert sorted(seqs) == list(range(1, total + 1)), f"seq 不连续：{sorted(seqs)[:10]}..."


def test_append_returns_unique_seq_under_concurrency(isolated_db):
    """并发下 append_session_event 返回的 seq SHALL 互不重复。"""
    sid = session_store.create_session(stock_code="600449", stock_name="宁夏建材", status="running")

    total = 40
    returned: list[int] = []
    errors: list[BaseException] = []

    def append(i: int) -> None:
        try:
            seq = session_store.append_session_event(
                sid, {"type": "thinking_token", "token": str(i)}
            )
            returned.append(seq)
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(append, range(total)))

    assert not errors, f"并发写抛出 {len(errors)} 个数据库异常"
    assert len(returned) == total
    assert len(set(returned)) == total, f"返回的 seq 有重复：{sorted(returned)}"
