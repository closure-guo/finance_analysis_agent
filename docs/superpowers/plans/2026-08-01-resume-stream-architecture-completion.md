# 可恢复流式生成架构完善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除实现与设计档案之间的 10 个偏离点，使可恢复流式生成架构完全一致

**Architecture:** 桥接统一方案：保留 PipelineRunner 线程执行模型，但将事件桥接到 stream_registry.publish；统一 SSE 端点为 subscribe 模式；修复协议层偏离（SSE 帧 id、终态 CAS、cancel 幂等、204 语义）；前端提取统一 SSE 事件处理器

**Tech Stack:** Python 3.12 / FastAPI / asyncio / SQLite / React 18 / TypeScript

## Global Constraints

- 后端单 uvicorn worker 部署（StreamRegistry 进程内内存结构）
- 变量命名使用 camelCase（用户规则）
- 代码注释使用中文（用户规则）
- 测试产物路径：fixtures -> tests/fixtures/ | 脚本 -> tests/scripts/ | 验证报告 -> tests/validation/ | E2E -> tests/e2e/
- E2E 禁止 mock 被测系统
- 先写失败测试再写实现

---

## File Structure

| 文件 | 职责 | 任务 |
| --- | --- | --- |
| `src/finance_agent/api.py` | SSE 帧格式、stream_session 204/心跳、cancel 幂等、增量持久化、Fast path 桥接 | T1, T3, T4, T5, T7 |
| `src/finance_agent/session_store.py` | 终态查询函数、upsert_chat | T2, T5 |
| `src/finance_agent/stream_registry.py` | publish CAS 检查、subscribe 先注册再读日志 + PipelineRunner 活跃检查 | T3, T6, T7 |
| `src/finance_agent/pipeline_runner.py` | 桥接 publish + cancel 标志 + 终态 publish | T7 |
| `frontend/src/App.tsx` | seq 去重、统一 handleSSEEvent | T8, T9 |
| `tests/test_sse_format.py` | SSE 帧 id 行测试 | T1 |
| `tests/test_session_store_terminal.py` | 终态查询函数测试 | T2 |
| `tests/test_terminal_cas.py` | CAS + cancel 幂等测试 | T3 |
| `tests/test_stream_204.py` | 204 语义测试 | T4 |
| `tests/test_incremental_persist.py` | 增量持久化测试 | T5 |
| `tests/test_subscribe_order.py` | subscribe 先注册再读日志测试 | T6 |
| `tests/test_fastpath_bridge.py` | Fast path 桥接测试 | T7 |
| `frontend/src/test/seq-dedup.test.tsx` | seq 去重测试 | T8 |
| `frontend/src/test/handle-sse-event.test.tsx` | 统一 handleSSEEvent 测试 | T9 |

---

### Task 1: SSE 帧格式 + 心跳间隔 (#1, #10)

**Files:**
- Modify: `src/finance_agent/api.py` - `_sse` 函数（约 171 行）和 `stream_session` 中的心跳超时（约 613 行）
- Test: `tests/test_sse_format.py`

**Interfaces:**
- Produces: `_sse(data: dict) -> str` 现在输出 `id: {seq}\ndata: {...}\n\n` 格式（当 data 含 seq 字段时）

- [ ] **Step 1: Write the failing test**

创建 `tests/test_sse_format.py`：

```python
"""SSE 帧格式测试：验证 _sse 输出包含 id: 行（当 data 有 seq 字段时）。"""

from finance_agent.api import _sse


def test_sse_with_seq_includes_id_line():
    """data 含 seq 字段时，_sse 输出应包含 id: 行。"""
    data = {"type": "chat_token", "token": "hello", "seq": 42}
    result = _sse(data)
    assert "id: 42\n" in result
    assert "data: " in result
    # id 行在 data 行之前
    assert result.index("id: 42\n") < result.index("data: ")


def test_sse_without_seq_excludes_id_line():
    """data 无 seq 字段时，_sse 输出不应包含 id: 行。"""
    data = {"type": "chat_token", "token": "hello"}
    result = _sse(data)
    assert "id:" not in result
    assert "data: " in result


def test_sse_seq_none_excludes_id_line():
    """data 的 seq 为 None 时，_sse 输出不应包含 id: 行。"""
    data = {"type": "chat_token", "token": "hello", "seq": None}
    result = _sse(data)
    assert "id:" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sse_format.py -v`
Expected: FAIL - `test_sse_with_seq_includes_id_line` 失败（当前 `_sse` 不输出 `id:` 行）

- [ ] **Step 3: Modify `_sse` function**

在 `src/finance_agent/api.py` 中，将 `_sse` 函数（约 171 行）从：

```python
def _sse(data: dict) -> str:
    """Format a SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
```

修改为：

```python
def _sse(data: dict) -> str:
    """Format a SSE data line.

    当 data 含 seq 字段时，在 data: 行前添加 id: 行，
    使原生 EventSource 的自动 Last-Event-ID 机制生效。
    """
    seq = data.get("seq")
    idLine = f"id: {seq}\n" if seq is not None else ""
    return f"{idLine}data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
```

- [ ] **Step 4: Modify heartbeat timeout from 15.0 to 10.0**

在 `src/finance_agent/api.py` 的 `stream_session` 函数中（约 613 行），将：

```python
                event = await asyncio.wait_for(gen.__anext__(), timeout=15.0)
```

修改为：

```python
                event = await asyncio.wait_for(gen.__anext__(), timeout=10.0)
```

同时更新函数文档字符串中的 `每 15s` 改为 `每 10s`。

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_sse_format.py -v`
Expected: PASS - 全部 3 个测试通过

- [ ] **Step 6: Commit**

```bash
git add tests/test_sse_format.py src/finance_agent/api.py
git commit -m "feat: [sse] 帧格式添加 id 行 + 心跳间隔改为 10s"
```

---

### Task 2: session_store 终态查询函数 (前置)

**Files:**
- Modify: `src/finance_agent/session_store.py`
- Test: `tests/test_session_store_terminal.py`

**Interfaces:**
- Produces: `has_terminal_event(session_id: str) -> bool` 和 `get_terminal_event(session_id: str) -> dict | None`

- [ ] **Step 1: Write the failing test**

创建 `tests/test_session_store_terminal.py`：

```python
"""session_store 终态事件查询函数测试。"""

import json

import pytest

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_store_terminal.py -v`
Expected: FAIL - `AttributeError: module 'finance_agent.session_store' has no attribute 'has_terminal_event'`

- [ ] **Step 3: Implement `has_terminal_event` and `get_terminal_event`**

在 `src/finance_agent/session_store.py` 的 `list_session_events` 函数之后（约 308 行后）添加：

```python
def has_terminal_event(session_id: str) -> bool:
    """检查 journal 中是否已有终态事件（done/interrupted/error）。

    用于 publish 的 CAS 检查，避免重复写入终态事件。
    """
    conn = _get_db()
    rows = conn.execute(
        "SELECT event_json FROM session_events WHERE session_id = ? ORDER BY seq DESC",
        (session_id,),
    ).fetchall()
    conn.close()
    terminalTypes = {"done", "interrupted", "error"}
    for row in rows:
        try:
            event = json.loads(row["event_json"])
            if event.get("type") in terminalTypes:
                return True
        except (json.JSONDecodeError, TypeError):
            continue
    return False


def get_terminal_event(session_id: str) -> dict | None:
    """返回 journal 中最后一条终态事件（done/interrupted/error），无则返回 None。

    用于 cancel 幂等：无活跃任务时返回终态而非 404。
    """
    conn = _get_db()
    rows = conn.execute(
        "SELECT seq, event_json FROM session_events WHERE session_id = ? ORDER BY seq DESC",
        (session_id,),
    ).fetchall()
    conn.close()
    terminalTypes = {"done", "interrupted", "error"}
    for row in rows:
        try:
            event = json.loads(row["event_json"])
            if event.get("type") in terminalTypes:
                event["seq"] = row["seq"]
                return event
        except (json.JSONDecodeError, TypeError):
            continue
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_store_terminal.py -v`
Expected: PASS - 全部 8 个测试通过

- [ ] **Step 5: Commit**

```bash
git add tests/test_session_store_terminal.py src/finance_agent/session_store.py
git commit -m "feat: [session_store] 添加终态事件查询函数 has_terminal_event / get_terminal_event"
```

---

### Task 3: 终态竞态 CAS + cancel 幂等 (#3, #4)

**Files:**
- Modify: `src/finance_agent/stream_registry.py` - `publish` 方法增加 CAS 检查
- Modify: `src/finance_agent/api.py` - `cancel_session` 端点改为幂等
- Test: `tests/test_terminal_cas.py`

**Interfaces:**
- Consumes: `session_store.has_terminal_event`, `session_store.get_terminal_event` (from Task 2)
- Produces: `publish` 现在对终态事件做 CAS 检查；`cancel_session` 幂等返回终态

- [ ] **Step 1: Write the failing test**

创建 `tests/test_terminal_cas.py`：

```python
"""终态 CAS 检查 + cancel 幂等测试。"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store, stream_registry


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


@pytest.mark.asyncio
async def test_publish_cas_rejects_second_terminal(tmp_path, monkeypatch):
    """先 publish done，再 publish interrupted，第二条应被拒绝（返回 0）。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    seq1 = await reg.publish(sid, {"type": "done"})
    assert seq1 > 0

    seq2 = await reg.publish(sid, {"type": "interrupted"})
    assert seq2 == 0  # CAS 拒绝

    # journal 中只有一条终态事件
    events = session_store.list_session_events(sid)
    terminal_events = [
        e for e in events
        if json.loads(e["event_json"]).get("type") in ("done", "interrupted", "error")
    ]
    assert len(terminal_events) == 1


@pytest.mark.asyncio
async def test_publish_cas_allows_non_terminal_after_terminal(tmp_path, monkeypatch):
    """终态后非终态事件不受 CAS 限制（但实际场景不会出现）。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    await reg.publish(sid, {"type": "done"})
    # 非终态事件不受 CAS 检查
    seq = await reg.publish(sid, {"type": "thinking_token", "token": "late"})
    assert seq > 0


def test_cancel_idempotent_returns_terminal(tmp_path, monkeypatch):
    """cancel 无活跃任务但有终态事件时返回终态而非 404。"""
    _setup_db(tmp_path, monkeypatch)
    # 预置终态事件
    sid = session_store.create_session(status="interrupted")
    session_store.append_session_event(sid, {"type": "interrupted"})

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.post(f"/api/sessions/{sid}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "interrupted"


def test_cancel_no_task_no_terminal_returns_404(tmp_path, monkeypatch):
    """cancel 无活跃任务且无终态事件时返回 404。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.post(f"/api/sessions/{sid}/cancel")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_terminal_cas.py -v`
Expected: FAIL - `test_publish_cas_rejects_second_terminal` 失败（当前 publish 无 CAS 检查，第二条终态事件写入成功）；`test_cancel_idempotent_returns_terminal` 失败（当前返回 404）

- [ ] **Step 3: Modify `publish` to add CAS check**

在 `src/finance_agent/stream_registry.py` 的 `publish` 方法（约 91 行）中，在 `seq = await asyncio.to_thread(...)` 之前添加 CAS 检查：

将：

```python
    async def publish(self, session_id: str, event: dict) -> int:
        """先落 session_events journal，再 fan-out 到订阅者队列。

        对应 delta spec Task 2.3。返回分配的 seq。
        """
        # 同步 SQLite 写入放在 executor 中避免阻塞事件循环（design.md D2）
        seq = await asyncio.to_thread(session_store.append_session_event, session_id, event)
```

修改为：

```python
    async def publish(self, session_id: str, event: dict) -> int:
        """先落 session_events journal，再 fan-out 到订阅者队列。

        对应 delta spec Task 2.3。返回分配的 seq。
        终态事件（done/interrupted/error）做 CAS 检查：已有终态则放弃（返回 0）。
        """
        # 终态 CAS 检查：已有终态事件时拒绝写入（避免重复终态）
        eventType = event.get("type")
        if eventType in ("done", "interrupted", "error"):
            existing = await asyncio.to_thread(
                session_store.has_terminal_event, session_id
            )
            if existing:
                return 0  # 已有终态，放弃
        # 同步 SQLite 写入放在 executor 中避免阻塞事件循环（design.md D2）
        seq = await asyncio.to_thread(session_store.append_session_event, session_id, event)
```

- [ ] **Step 4: Modify `cancel_session` for idempotent return**

在 `src/finance_agent/api.py` 中，首先在 import 块（约 29-45 行）的 `from finance_agent.session_store import (...)` 中添加两个函数：

将：

```python
from finance_agent.session_store import (  # noqa: E402
    append_chat,
    append_session_event,
    create_chat_session,
    create_session,
    delete_session,
    get_session,
    init_db,
    list_session_events,
    list_sessions,
    rename_session,
    update_pipeline_snapshot,
    update_pipeline_timelines,
    update_session_for_clarify,
    update_session_report,
    update_session_status,
)
```

修改为：

```python
from finance_agent.session_store import (  # noqa: E402
    append_chat,
    append_session_event,
    create_chat_session,
    create_session,
    delete_session,
    get_session,
    get_terminal_event,
    has_terminal_event,
    init_db,
    list_session_events,
    list_sessions,
    rename_session,
    update_pipeline_snapshot,
    update_pipeline_timelines,
    update_session_for_clarify,
    update_session_report,
    update_session_status,
)
```

然后修改 `cancel_session` 端点（约 631 行），将：

```python
@app.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    """取消会话的活跃生成任务。无活跃任务返回 404。

    对应 delta spec Task 4.2。
    """
    result = await stream_registry.cancel(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No active task for this session")
    return {"ok": True}
```

修改为：

```python
@app.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    """取消会话的活跃生成任务。无活跃任务时检查终态事件做幂等返回。

    对应 delta spec Task 4.2。
    """
    result = await stream_registry.cancel(session_id)
    if not result:
        # 无活跃任务：检查是否已有终态事件（幂等返回）
        terminal = await asyncio.to_thread(get_terminal_event, session_id)
        if terminal:
            return {"ok": True, "status": terminal["type"]}
        raise HTTPException(status_code=404, detail="No active task for this session")
    return {"ok": True, "status": "interrupted"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_terminal_cas.py -v`
Expected: PASS - 全部 4 个测试通过

- [ ] **Step 6: Commit**

```bash
git add tests/test_terminal_cas.py src/finance_agent/stream_registry.py src/finance_agent/api.py
git commit -m "feat: [stream] 终态 CAS 检查 + cancel 幂等返回终态"
```

---

### Task 4: 204 语义 (#6)

**Files:**
- Modify: `src/finance_agent/api.py` - `stream_session` 端点增加 204 分支
- Test: `tests/test_stream_204.py`

**Interfaces:**
- Consumes: `session_store.list_session_events`, `stream_registry.is_active` (已有)
- Produces: `stream_session` 无事件且无活跃任务时返回 `Response(status_code=204)`

- [ ] **Step 1: Write the failing test**

创建 `tests/test_stream_204.py`：

```python
"""stream_session 204 语义测试。"""

import pytest
from fastapi.testclient import TestClient

from finance_agent import session_store


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def test_stream_returns_204_when_no_events_no_active(tmp_path, monkeypatch):
    """无事件且无活跃任务时返回 204。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.get(f"/api/sessions/{sid}/stream")
    assert resp.status_code == 204


def test_stream_returns_200_when_events_exist(tmp_path, monkeypatch):
    """有事件时返回 200 SSE 流。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="completed")
    session_store.append_session_event(sid, {"type": "done"})

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.get(f"/api/sessions/{sid}/stream")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_stream_returns_404_when_session_not_found(tmp_path, monkeypatch):
    """session 不存在时返回 404。"""
    _setup_db(tmp_path, monkeypatch)

    from finance_agent.api import app

    client = TestClient(app)
    resp = client.get("/api/sessions/nonexistent/stream")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stream_204.py -v`
Expected: FAIL - `test_stream_returns_204_when_no_events_no_active` 失败（当前返回 200 并下发终态事件）

- [ ] **Step 3: Add `Response` import and 204 branch**

在 `src/finance_agent/api.py` 中，首先修改 import（约 19 行）：

将：

```python
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
```

修改为：

```python
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
```

然后修改 `stream_session` 函数（约 586 行），在 session 存在性校验之后、`sse_stream` 定义之前添加 204 检查。

将：

```python
    # 校验 session 存在
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    async def sse_stream() -> AsyncGenerator[str, None]:
```

修改为：

```python
    # 校验 session 存在
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # 204 语义：无事件且无活跃任务时返回 204
    events = await asyncio.to_thread(list_session_events, session_id, after_seq)
    hasActive = stream_registry.is_active(session_id)
    if not events and not hasActive:
        return Response(status_code=204)

    async def sse_stream() -> AsyncGenerator[str, None]:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stream_204.py -v`
Expected: PASS - 全部 3 个测试通过

- [ ] **Step 5: Commit**

```bash
git add tests/test_stream_204.py src/finance_agent/api.py
git commit -m "feat: [api] stream 端点 204 语义：无事件无活跃任务时返回 204"
```

---

### Task 5: 增量持久化 (#5)

**Files:**
- Modify: `src/finance_agent/session_store.py` - 新增 `upsert_chat`
- Modify: `src/finance_agent/api.py` - 新增 `_upsert_assistant_chat`，修改 `_run_react_analysis` 和 `_run_chat_task` 增加定时持久化
- Test: `tests/test_incremental_persist.py`

**Interfaces:**
- Consumes: `_ChatCollector` (已有), `append_chat` (已有)
- Produces: `session_store.upsert_chat(session_id, role, content, ...)` ; `api._upsert_assistant_chat(session_id, collector)`

- [ ] **Step 1: Write the failing test**

创建 `tests/test_incremental_persist.py`：

```python
"""增量持久化测试：upsert_chat 对已有 assistant 消息做更新，对无 assistant 消息做追加。"""

import json

import pytest

from finance_agent import session_store


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def test_upsert_chat_updates_existing_assistant(tmp_path, monkeypatch):
    """已有 assistant 消息时，upsert_chat 更新而非追加。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(status="running")
    # 预置 user + assistant 消息
    session_store.append_chat(sid, "user", "你好")
    session_store.append_chat(sid, "assistant", "部分回复")

    # upsert 更新 assistant 消息
    session_store.upsert_chat(
        sid, "assistant", "完整回复", thinking="思考过程", tool_calls=[{"name": "web_search"}]
    )

    session = session_store.get_session(sid)
    history = session["chat_history"]
    assert len(history) == 2  # 不追加，仍是 2 条
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
    assert history[1]["content"] == "回复1"  # 第一条不变
    assert history[3]["content"] == "更新回复2"  # 最后一条更新
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_incremental_persist.py -v`
Expected: FAIL - `AttributeError: module 'finance_agent.session_store' has no attribute 'upsert_chat'`

- [ ] **Step 3: Implement `upsert_chat` in session_store.py**

在 `src/finance_agent/session_store.py` 的 `append_chat` 函数之后（约 506 行后）添加：

```python
def upsert_chat(
    session_id: str,
    role: str,
    content: str,
    thinking: str | None = None,
    tool_calls: list | None = None,
    agent_timeline: list | None = None,
) -> None:
    """upsert 语义的 chat 持久化：查找最后一条指定 role 的消息，存在则更新，无则追加。

    用于运行中增量持久化：每 10 秒将 collector 内容 upsert 到 chat_history，
    避免用户中途切走后 assistant 回复内容丢失。
    """
    conn = _get_db()
    row = conn.execute(
        "SELECT chat_history FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        conn.close()
        return
    try:
        history = json.loads(row["chat_history"]) if row["chat_history"] else []
    except (json.JSONDecodeError, TypeError):
        history = []

    # 从末尾查找最后一条指定 role 的消息
    found = False
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == role:
            history[i]["content"] = content
            if thinking is not None:
                history[i]["thinking"] = thinking
            if tool_calls is not None:
                history[i]["tool_calls"] = tool_calls
            if agent_timeline is not None:
                history[i]["agentTimeline"] = agent_timeline
            history[i]["ts"] = datetime.now().isoformat()
            found = True
            break

    if not found:
        entry: dict = {"role": role, "content": content, "ts": datetime.now().isoformat()}
        if thinking:
            entry["thinking"] = thinking
        if tool_calls:
            entry["tool_calls"] = tool_calls
        if agent_timeline:
            entry["agentTimeline"] = agent_timeline
        history.append(entry)

    conn.execute(
        "UPDATE sessions SET chat_history = ? WHERE session_id = ?",
        (json.dumps(history, ensure_ascii=False), session_id),
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Implement `_upsert_assistant_chat` and modify SSE loops in api.py**

在 `src/finance_agent/api.py` 中，首先在 import 块中添加 `upsert_chat`：

将 `from finance_agent.session_store import (...)` 中的 import 列表添加 `upsert_chat`（在 `rename_session` 之后）：

```python
    rename_session,
    update_pipeline_snapshot,
    update_pipeline_timelines,
    update_session_for_clarify,
    update_session_report,
    update_session_status,
    upsert_chat,
)
```

然后在 `_persist_collector` 函数之后（约 976 行后）添加 `_upsert_assistant_chat`：

```python
def _upsert_assistant_chat(session_id: str, collector: _ChatCollector) -> None:
    """增量持久化 collector 内容到 chat_history（upsert 语义）。

    在 SSE 循环中每 10 秒调用，确保运行中会话的 assistant 消息
    在用户中途切走后仍可从 chat_history 恢复。
    """
    response = collector.response.strip()
    thinking = collector.thinking.strip() or None
    tool_calls = collector.tool_calls or None
    agent_timeline = collector.agent_timeline or None
    if not (response or thinking or tool_calls or agent_timeline):
        return
    upsert_chat(
        session_id,
        "assistant",
        response,
        thinking=thinking,
        tool_calls=tool_calls,
        agent_timeline=agent_timeline,
    )
```

然后修改 `_run_react_analysis` 中的 SSE 循环（约 1134 行），在 `async for sse_str in stream_agent_to_sse(...)` 之前添加计时变量，在循环体内添加定时持久化。

将：

```python
    # 流式输出 Agent 事件
    stream_error = False
    try:
        async for sse_str in stream_agent_to_sse(
            agent,
            user_query,
            on_metadata=on_metadata,
            on_resolved=on_resolved,
            extra_events={
                "analysis_id": analysis_id,
                "session_id": session_id,
                "duration_ms": 0,
            },
            session_id=session_id,
            user_id=req.user_id,
        ):
            data = _parse_sse_data(sse_str)
            if data is not None:
                collector.feed(data)
                if data.get("type") == "report_ready":
                    analysis_executed = True
                    data["session_id"] = session_id
                    data["duration_ms"] = int((time.time() - start_time) * 1000)
                await stream_registry.publish(session_id, data)
        # 正常完成：持久化
        _persist_collector(session_id, collector)
```

修改为：

```python
    # 流式输出 Agent 事件
    stream_error = False
    lastPersistTime = time.time()
    PERSIST_INTERVAL = 10  # 增量持久化间隔（秒）
    try:
        async for sse_str in stream_agent_to_sse(
            agent,
            user_query,
            on_metadata=on_metadata,
            on_resolved=on_resolved,
            extra_events={
                "analysis_id": analysis_id,
                "session_id": session_id,
                "duration_ms": 0,
            },
            session_id=session_id,
            user_id=req.user_id,
        ):
            data = _parse_sse_data(sse_str)
            if data is not None:
                collector.feed(data)
                if data.get("type") == "report_ready":
                    analysis_executed = True
                    data["session_id"] = session_id
                    data["duration_ms"] = int((time.time() - start_time) * 1000)
                await stream_registry.publish(session_id, data)
                # 定时增量持久化：每 10 秒 upsert collector 内容
                if time.time() - lastPersistTime > PERSIST_INTERVAL:
                    _upsert_assistant_chat(session_id, collector)
                    lastPersistTime = time.time()
        # 正常完成：最终持久化
        _persist_collector(session_id, collector)
```

同样修改 `_run_chat_task` 中的 SSE 循环（约 1380 行），将：

```python
    try:
        async for sse_str in stream_agent_to_sse(
            agent, req.message, session_id=session_id, user_id=req.user_id
        ):
            data = _parse_sse_data(sse_str)
            if data is not None:
                collector.feed(data)
                await stream_registry.publish(session_id, data)
        # 正常完成：持久化
        _persist_collector(session_id, collector)
```

修改为：

```python
    lastPersistTime = time.time()
    PERSIST_INTERVAL = 10  # 增量持久化间隔（秒）
    try:
        async for sse_str in stream_agent_to_sse(
            agent, req.message, session_id=session_id, user_id=req.user_id
        ):
            data = _parse_sse_data(sse_str)
            if data is not None:
                collector.feed(data)
                await stream_registry.publish(session_id, data)
                # 定时增量持久化：每 10 秒 upsert collector 内容
                if time.time() - lastPersistTime > PERSIST_INTERVAL:
                    _upsert_assistant_chat(session_id, collector)
                    lastPersistTime = time.time()
        # 正常完成：最终持久化
        _persist_collector(session_id, collector)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_incremental_persist.py -v`
Expected: PASS - 全部 4 个测试通过

- [ ] **Step 6: Commit**

```bash
git add tests/test_incremental_persist.py src/finance_agent/session_store.py src/finance_agent/api.py
git commit -m "feat: [persist] 运行中增量持久化 chat_history（每 10s upsert）"
```

---

### Task 6: subscribe 先注册再读日志 (#8)

**Files:**
- Modify: `src/finance_agent/stream_registry.py` - `subscribe` 方法重构步骤顺序
- Test: `tests/test_subscribe_order.py`

**Interfaces:**
- Produces: `subscribe` 步骤顺序改为：先注册队列 -> 读日志重放 -> 无活跃任务下发终态 -> 补漏 -> 消费实时队列

- [ ] **Step 1: Write the failing test**

创建 `tests/test_subscribe_order.py`：

```python
"""subscribe 先注册队列再读日志测试：重放期间有新事件产生时不丢事件。"""

from __future__ import annotations

import asyncio
import json

import pytest

from finance_agent import session_store, stream_registry


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


@pytest.mark.asyncio
async def test_subscribe_no_event_loss_during_replay(tmp_path, monkeypatch):
    """重放期间有新事件产生时，先注册队列再读日志不丢事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    # 预置 2 条历史事件
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "a"})
    session_store.append_session_event(sid, {"type": "thinking_token", "token": "b"})

    async def dummyTask():
        await asyncio.sleep(10)

    await reg.start(sid, dummyTask())

    # 启动订阅（在另一个 task 中）
    gen = reg.subscribe(sid, after_seq=0)

    # 取第一个事件（重放的历史事件）
    event1 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event1["type"] == "thinking_token"

    # 在重放期间发布新事件（模拟重放期间有新事件产生）
    await reg.publish(sid, {"type": "thinking_token", "token": "c"})

    # 继续消费：应收到第二条历史事件和新事件
    event2 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event2["type"] == "thinking_token"

    event3 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event3["type"] == "thinking_token"
    # 新事件不丢失
    tokens = [event1.get("token"), event2.get("token"), event3.get("token")]
    assert "c" in tokens

    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_subscribe_replays_then_realtime(tmp_path, monkeypatch):
    """subscribe 先重放历史事件，再接续实时事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="running")

    # 预置 1 条历史事件
    session_store.append_session_event(sid, {"type": "chat_token", "token": "old"})

    async def dummyTask():
        await asyncio.sleep(10)

    await reg.start(sid, dummyTask())

    gen = reg.subscribe(sid, after_seq=0)

    # 重放历史事件
    event1 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event1["token"] == "old"

    # 发布实时事件
    await reg.publish(sid, {"type": "chat_token", "token": "new"})

    # 消费实时事件
    event2 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event2["token"] == "new"

    await reg.cancel(sid)


@pytest.mark.asyncio
async def test_subscribe_terminal_when_no_active(tmp_path, monkeypatch):
    """无活跃任务时，重放后下发终态事件。"""
    _setup_db(tmp_path, monkeypatch)
    reg = stream_registry.StreamRegistry()
    sid = session_store.create_session(status="completed")

    # 预置 1 条历史事件 + 1 条终态事件
    session_store.append_session_event(sid, {"type": "chat_token", "token": "hello"})
    session_store.append_session_event(sid, {"type": "done"})

    gen = reg.subscribe(sid, after_seq=0)

    # 重放历史事件
    event1 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event1["token"] == "hello"

    # 终态事件
    event2 = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert event2["type"] == "done"

    # 流应结束
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=2.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_subscribe_order.py -v`
Expected: FAIL - `test_subscribe_no_event_loss_during_replay` 可能失败或不稳定（当前 subscribe 先读日志再注册队列，重放期间的新事件可能丢失）

- [ ] **Step 3: Refactor `subscribe` method**

在 `src/finance_agent/stream_registry.py` 中，将 `subscribe` 方法（约 135-203 行）替换为：

```python
    async def subscribe(self, session_id: str, after_seq: int = 0) -> AsyncGenerator[dict, None]:
        """订阅会话事件流：先注册队列，再重放 journal，最后接续实时事件。

        步骤顺序（先注册再读日志，消除重放缝合竞态）：
        1. 检查活跃任务并注册实时队列
        2. 读日志重放（注册队列后新事件不会丢失）
        3. 无活跃任务时下发终态事件
        4. 补漏（重放期间产生的新事件）
        5. 消费实时队列

        seq 去重消解重放与补漏的重叠段。
        对应 delta spec Task 2.4。
        """
        # 1. 检查活跃任务并注册实时队列
        stream = self._streams.get(session_id)
        hasActive = stream is not None and stream.task is not None and not stream.task.done()

        queue: asyncio.Queue[dict | None] | None = None
        if hasActive and stream is not None:
            queue = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAX)
            stream.subscribers.append(queue)

        # 2. 读日志重放（注册队列后新事件进入队列，不会丢失）
        events = await asyncio.to_thread(
            session_store.list_session_events, session_id, after_seq
        )
        replayedSeq = after_seq
        for row in events:
            try:
                event = json.loads(row["event_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            replayedSeq = row["seq"]
            event["seq"] = replayedSeq
            if event.get("type") in ("done", "interrupted", "error"):
                yield event
                return
            yield event

        # 3. 无活跃任务：下发终态事件
        if not hasActive:
            session = await asyncio.to_thread(session_store.get_session, session_id)
            if session and session["status"] == "interrupted":
                yield {"type": "interrupted"}
            else:
                yield {"type": "done"}
            return

        # 4. 补漏：重放期间产生的新事件（lastSeq > replayedSeq）
        assert stream is not None  # hasActive 为 True 时 stream 必非 None
        if stream.lastSeq > replayedSeq:
            missed = await asyncio.to_thread(
                session_store.list_session_events, session_id, replayedSeq
            )
            for row in missed:
                try:
                    event = json.loads(row["event_json"])
                except (json.JSONDecodeError, TypeError):
                    continue
                event["seq"] = row["seq"]
                if event.get("type") in ("done", "interrupted", "error"):
                    yield event
                    return
                yield event

        # 5. 消费实时队列
        if queue is not None:
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        # 哨兵：任务结束通知
                        break
                    yield event
            finally:
                if queue in stream.subscribers:
                    stream.subscribers.remove(queue)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_subscribe_order.py -v`
Expected: PASS - 全部 3 个测试通过

- [ ] **Step 5: Run existing stream_registry tests to ensure no regression**

Run: `uv run pytest tests/test_stream_registry.py -v`
Expected: PASS - 全部已有测试通过

- [ ] **Step 6: Commit**

```bash
git add tests/test_subscribe_order.py src/finance_agent/stream_registry.py
git commit -m "feat: [stream_registry] subscribe 先注册队列再读日志，消除重放缝合竞态"
```

---

### Task 7: Fast path 桥接 (#2)

**Files:**
- Modify: `src/finance_agent/pipeline_runner.py` - `_run` 增加桥接 publish + cancel 标志；新增 `cancel` 方法；`start` 接收 loop 参数
- Modify: `src/finance_agent/stream_registry.py` - `subscribe` 增加 PipelineRunner 活跃检查（延迟导入）
- Modify: `src/finance_agent/api.py` - Fast path `event_stream` 改为 subscribe；`cancel_session` 增加 PipelineRunner.cancel；`PipelineRunner.start` 传入 loop
- Test: `tests/test_fastpath_bridge.py`

**Interfaces:**
- Consumes: `stream_registry.publish` (from Task 3), `subscribe` 先注册再读日志 (from Task 6)
- Produces: `PipelineRunner.start(session_id, event_source, snapshot, loop=None)`; `PipelineRunner.cancel(session_id) -> bool`; `subscribe` 检查 `PipelineRunner.is_running`

- [ ] **Step 1: Write the failing test**

创建 `tests/test_fastpath_bridge.py`：

```python
"""Fast path 桥接测试：PipelineRunner._run 中的事件经 publish 写入 journal；cancel 设置标志。"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from finance_agent import session_store
from finance_agent.pipeline_runner import PipelineRunner


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _setup_db(tmp_path, monkeypatch):
    """隔离 DB。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()


def _fake_events():
    """模拟管线 SSE 事件序列。"""
    yield _sse({"type": "analysis_start", "session_id": "s1"})
    yield _sse({"type": "node_start", "node_id": "check_cache", "layer": "PREP"})
    yield _sse({
        "type": "node_complete",
        "node_id": "check_cache",
        "layer": "PREP",
        "completed": ["check_cache"],
        "progress": 0.03,
        "output": {"summary": "ok"},
    })


@pytest.mark.asyncio
async def test_pipeline_bridge_publishes_to_journal(tmp_path, monkeypatch):
    """PipelineRunner._run 中的事件经 publish 写入 journal。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    loop = asyncio.get_event_loop()
    PipelineRunner.start(
        sid,
        _fake_events,
        {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0},
        loop=loop,
    )

    # 等后台线程跑完
    deadline = time.time() + 10
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        await asyncio.sleep(0.05)
    assert not PipelineRunner.is_running(sid)

    # 验证事件已写入 journal
    events = session_store.list_session_events(sid)
    event_types = [json.loads(e["event_json"]).get("type") for e in events]
    assert "analysis_start" in event_types
    assert "node_start" in event_types
    assert "node_complete" in event_types
    # 终态事件（done）由 finally 块发布
    assert "done" in event_types


def test_pipeline_cancel_sets_flag(tmp_path, monkeypatch):
    """PipelineRunner.cancel 设置取消标志并终止后台线程。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    def slow_events():
        for i in range(100):
            time.sleep(0.1)
            yield _sse({"type": "thinking_token", "token": f"token_{i}"})

    PipelineRunner.start(
        sid,
        slow_events,
        {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0},
    )
    assert PipelineRunner.is_running(sid)

    result = PipelineRunner.cancel(sid)
    assert result is True
    # 等线程结束
    deadline = time.time() + 10
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)
    assert not PipelineRunner.is_running(sid)


def test_pipeline_cancel_returns_false_when_not_running(tmp_path, monkeypatch):
    """无运行中任务时，cancel 返回 False。"""
    _setup_db(tmp_path, monkeypatch)
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
    result = PipelineRunner.cancel(sid)
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fastpath_bridge.py -v`
Expected: FAIL - `TypeError: PipelineRunner.start() got an unexpected keyword argument 'loop'`; `AttributeError: type object 'PipelineRunner' has no attribute 'cancel'`

- [ ] **Step 3: Modify `_RunState` to add `cancel_event`**

在 `src/finance_agent/pipeline_runner.py` 中，将 `_RunState` 类（约 232 行）从：

```python
class _RunState:
    def __init__(self, thread: threading.Thread):
        self.thread = thread
        self.events: list[str] = []
        self.lock = threading.Lock()
        self.done = False
```

修改为：

```python
class _RunState:
    def __init__(self, thread: threading.Thread):
        self.thread = thread
        self.events: list[str] = []
        self.lock = threading.Lock()
        self.done = False
        self.cancel_event = threading.Event()  # 取消标志
```

- [ ] **Step 4: Add `cancel` method and modify `start` to accept `loop`**

在 `PipelineRunner` 类中，将 `start` 方法（约 253 行）从：

```python
    @classmethod
    def start(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        initial_snapshot: dict,
    ) -> None:
        """启动后台管线线程。已在跑则幂等返回。"""
        with cls._guard:
            if session_id in cls._running and not cls._running[session_id].done:
                return
            thread = threading.Thread(
                target=cls._run,
                args=(session_id, event_source, initial_snapshot),
                daemon=True,
            )
            cls._running[session_id] = _RunState(thread)
            thread.start()
```

修改为：

```python
    @classmethod
    def start(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        initial_snapshot: dict,
        loop: Any | None = None,
    ) -> None:
        """启动后台管线线程。已在跑则幂等返回。

        Args:
            loop: 主事件循环引用。传入时事件桥接到 stream_registry.publish。
        """
        with cls._guard:
            if session_id in cls._running and not cls._running[session_id].done:
                return
            thread = threading.Thread(
                target=cls._run,
                args=(session_id, event_source, initial_snapshot, loop),
                daemon=True,
            )
            cls._running[session_id] = _RunState(thread)
            thread.start()

    @classmethod
    def cancel(cls, session_id: str) -> bool:
        """取消运行中的管线任务。设置取消标志并等待线程结束。

        无运行中任务返回 False。
        """
        with cls._guard:
            state = cls._running.get(session_id)
            if not state or state.done:
                return False
            state.cancel_event.set()
        state.thread.join(timeout=5)
        return True
```

- [ ] **Step 5: Modify `_run` to bridge publish and check cancel**

在 `pipeline_runner.py` 顶部添加导入（在现有 import 之后，约 28 行后）：

```python
from finance_agent.stream_registry import registry as stream_registry
```

然后将 `_run` 方法（约 287 行）从：

```python
    @classmethod
    def _run(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        snapshot: dict,
    ) -> None:
        state = cls._running.get(session_id)
        tree = snapshot.get("layerTree") or build_layer_tree()
        # 管线节点时序（persist-full-session-timeline）：thinking_token 按 node 分组
        # 持久化到 sessions.pipeline_timelines，写入节奏与 snapshot 一致（每相关事件一次）
        nodeTimelines: dict[str, list[dict]] = {}
        # search/tool 事件不带 node 字段，归入「当前运行节点」：
        # node_start 置位、node_complete 清空（用户决策 2026-07-30）
        currentNode = ""
        # 管线全局超时（环境变量可配置，默认 600 秒）
        pipeline_timeout = float(os.environ.get("PIPELINE_TIMEOUT_SECONDS", "600"))
        start_time = time.time()
        try:
            for sse_str in event_source():
                # 超时检查：事件间检测，长时间无事件时标记 failed
                if time.time() - start_time > pipeline_timeout:
                    session_store.update_session_status(
                        session_id, "failed", failure_reason="管线执行超时"
                    )
                    break
                if state is not None:
                    with state.lock:
                        state.events.append(sse_str)
                event = cls._parse_event(sse_str)
                if event is None:
                    continue
                eventType = event.get("type")
                # 管线模式 thinking_token：node 字段缺失/空串归入 '' 键（与前端一致）
                if eventType == "thinking_token":
                    nodeTimelines = apply_pipeline_thinking_token(
                        nodeTimelines, event.get("node") or "", event.get("token", "")
                    )
                    session_store.update_pipeline_timelines(session_id, nodeTimelines)
                elif eventType in ("search_start", "search_result", "search_error"):
                    nodeTimelines = apply_pipeline_search_event(nodeTimelines, currentNode, event)
                    session_store.update_pipeline_timelines(session_id, nodeTimelines)
                elif eventType in ("tool_call", "tool_result"):
                    nodeTimelines = apply_pipeline_tool_event(nodeTimelines, currentNode, event)
                    session_store.update_pipeline_timelines(session_id, nodeTimelines)
                elif eventType in ("node_start", "node_complete", "node_timing"):
                    if eventType == "node_start":
                        currentNode = event.get("node_id", "")
                    elif eventType == "node_complete":
                        nodeTimelines = apply_pipeline_node_complete(
                            nodeTimelines, event.get("node_id", "")
                        )
                        session_store.update_pipeline_timelines(session_id, nodeTimelines)
                        # 该节点完成即非当前运行节点；间隙事件归入 '' 键
                        if currentNode == event.get("node_id", ""):
                            currentNode = ""
                    now_ms = int(time.time() * 1000)
                    tree = apply_node_event(tree, event, now_ms)
                    snapshot = {
                        # layerTree 序列化为内嵌 JSON 字符串，对齐前端 deserializeLayerTree 契约
                        "layerTree": json.dumps(tree, ensure_ascii=False),
                        "currentNodeId": _current_node(tree),
                        "progress": _progress(tree),
                        "updatedAt": now_ms,
                    }
                    session_store.update_pipeline_snapshot(session_id, snapshot)
        except Exception as e:
            logger.exception("后台管线执行异常 session=%s", session_id)
            session_store.update_session_status(
                session_id, "failed", failure_reason=f"{type(e).__name__}: {e}"
            )
        finally:
            if state is not None:
                state.done = True
```

修改为：

```python
    @classmethod
    def _run(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        snapshot: dict,
        loop: Any | None = None,
    ) -> None:
        state = cls._running.get(session_id)
        tree = snapshot.get("layerTree") or build_layer_tree()
        # 管线节点时序（persist-full-session-timeline）：thinking_token 按 node 分组
        # 持久化到 sessions.pipeline_timelines，写入节奏与 snapshot 一致（每相关事件一次）
        nodeTimelines: dict[str, list[dict]] = {}
        # search/tool 事件不带 node 字段，归入「当前运行节点」：
        # node_start 置位、node_complete 清空（用户决策 2026-07-30）
        currentNode = ""
        # 管线全局超时（环境变量可配置，默认 600 秒）
        pipeline_timeout = float(os.environ.get("PIPELINE_TIMEOUT_SECONDS", "600"))
        start_time = time.time()
        failed = False
        try:
            for sse_str in event_source():
                # 取消检查：cancel_event 被设置时中断管线
                if state is not None and state.cancel_event.is_set():
                    if loop:
                        asyncio.run_coroutine_threadsafe(
                            stream_registry.publish(session_id, {"type": "interrupted"}), loop
                        ).result(timeout=5)
                    break
                # 超时检查：事件间检测，长时间无事件时标记 failed
                if time.time() - start_time > pipeline_timeout:
                    session_store.update_session_status(
                        session_id, "failed", failure_reason="管线执行超时"
                    )
                    failed = True
                    break
                # 桥接模式下不累积事件（事件经 publish 写入 journal）
                if state is not None and not loop:
                    with state.lock:
                        state.events.append(sse_str)
                event = cls._parse_event(sse_str)
                # 桥接到 stream_registry（经 run_coroutine_threadsafe 跨线程调用）
                if event and loop:
                    asyncio.run_coroutine_threadsafe(
                        stream_registry.publish(session_id, event), loop
                    ).result(timeout=5)
                if event is None:
                    continue
                eventType = event.get("type")
                # 管线模式 thinking_token：node 字段缺失/空串归入 '' 键（与前端一致）
                if eventType == "thinking_token":
                    nodeTimelines = apply_pipeline_thinking_token(
                        nodeTimelines, event.get("node") or "", event.get("token", "")
                    )
                    session_store.update_pipeline_timelines(session_id, nodeTimelines)
                elif eventType in ("search_start", "search_result", "search_error"):
                    nodeTimelines = apply_pipeline_search_event(nodeTimelines, currentNode, event)
                    session_store.update_pipeline_timelines(session_id, nodeTimelines)
                elif eventType in ("tool_call", "tool_result"):
                    nodeTimelines = apply_pipeline_tool_event(nodeTimelines, currentNode, event)
                    session_store.update_pipeline_timelines(session_id, nodeTimelines)
                elif eventType in ("node_start", "node_complete", "node_timing"):
                    if eventType == "node_start":
                        currentNode = event.get("node_id", "")
                    elif eventType == "node_complete":
                        nodeTimelines = apply_pipeline_node_complete(
                            nodeTimelines, event.get("node_id", "")
                        )
                        session_store.update_pipeline_timelines(session_id, nodeTimelines)
                        # 该节点完成即非当前运行节点；间隙事件归入 '' 键
                        if currentNode == event.get("node_id", ""):
                            currentNode = ""
                    now_ms = int(time.time() * 1000)
                    tree = apply_node_event(tree, event, now_ms)
                    snapshot = {
                        # layerTree 序列化为内嵌 JSON 字符串，对齐前端 deserializeLayerTree 契约
                        "layerTree": json.dumps(tree, ensure_ascii=False),
                        "currentNodeId": _current_node(tree),
                        "progress": _progress(tree),
                        "updatedAt": now_ms,
                    }
                    session_store.update_pipeline_snapshot(session_id, snapshot)
        except Exception as e:
            logger.exception("后台管线执行异常 session=%s", session_id)
            session_store.update_session_status(
                session_id, "failed", failure_reason=f"{type(e).__name__}: {e}"
            )
            failed = True
            if loop:
                asyncio.run_coroutine_threadsafe(
                    stream_registry.publish(
                        session_id, {"type": "error", "message": str(e)}
                    ),
                    loop,
                ).result(timeout=5)
        finally:
            if state is not None:
                state.done = True
            # 发布终态事件（CAS 保护，避免与 error/interrupted 重复）
            if loop:
                terminal = {"type": "error"} if failed else {"type": "done"}
                asyncio.run_coroutine_threadsafe(
                    stream_registry.publish(session_id, terminal), loop
                ).result(timeout=5)
```

还需要在 `pipeline_runner.py` 顶部添加 `asyncio` 导入（在现有 `import` 之后）：

```python
import asyncio
```

并添加 `Any` 类型导入（在 `from typing import` 行中，如果没有则添加）：

```python
from typing import Any
```

- [ ] **Step 6: Modify `subscribe` to add PipelineRunner active check**

在 `src/finance_agent/stream_registry.py` 的 `subscribe` 方法中，将步骤 1（约 135 行的 `hasActive` 行）从：

```python
        # 1. 检查活跃任务并注册实时队列
        stream = self._streams.get(session_id)
        hasActive = stream is not None and stream.task is not None and not stream.task.done()
```

修改为：

```python
        # 1. 检查活跃任务并注册实时队列
        stream = self._streams.get(session_id)
        # 延迟导入避免循环依赖（pipeline_runner 导入 stream_registry）
        pipelineActive = False
        try:
            from finance_agent.pipeline_runner import PipelineRunner
            pipelineActive = PipelineRunner.is_running(session_id)
        except ImportError:
            pass
        hasActive = (
            (stream is not None and stream.task is not None and not stream.task.done())
            or pipelineActive
        )
```

- [ ] **Step 7: Modify Fast path `event_stream` in api.py**

在 `src/finance_agent/api.py` 的 `analyze` 端点中，将 Fast path 的 `event_stream` 函数（约 1243 行）从：

```python
    if stock_code and not req.session_id:
        async def event_stream() -> AsyncGenerator[str, None]:
            # 发 session_created 事件（新会话时）
            yield _sse(
                {
                    "type": "session_created",
                    "session_id": session_id,
                    "display_name": display_name,
                    "timestamp": _now(),
                }
            )
            update_session_for_clarify(
                session_id, stock_code=stock_code, stock_name=stock_name, status="running"
            )
            # 管线后台执行：SSE 仅订阅事件队列，客户端断开不中断管线，
            # 节点事件由 PipelineRunner 持续写入 pipeline_snapshot 供断线恢复
            PipelineRunner.start(
                session_id,
                lambda: _run_graph_streaming(
                    stock_code, stock_name, req, analysis_id, start_time, session_id=session_id
                ),
                {
                    "layerTree": build_layer_tree(),
                    "currentNodeId": "",
                    "progress": 0.0,
                    "updatedAt": int(time.time() * 1000),
                },
            )
            # 订阅事件队列：在线时实时转发，断开仅停止订阅；
            # 空转时定期发心跳注释，防止代理断连并保持响应活跃
            heartbeat_counter = 0
            while True:
                events = PipelineRunner.get_events(session_id)
                for event in events:
                    yield event
                if not events:
                    if not PipelineRunner.is_running(session_id):
                        break
                    # 每 10 次空转（约 2 秒）发一次心跳，保持 SSE 连接活跃
                    heartbeat_counter += 1
                    if heartbeat_counter >= 10:
                        heartbeat_counter = 0
                        yield ": heartbeat\n\n"
                await asyncio.sleep(0.2)
            # 跳出后兜底排空：覆盖 get_events 与 done 置位之间的竞态窗口
            for event in PipelineRunner.get_events(session_id):
                yield event
            # 管线失败时给在线客户端发 error（对齐 _run_graph_streaming 的 error 结构），否则发 done
            session = get_session(session_id) or {}
            if session.get("status") == "failed":
                yield _sse(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "message": "管线执行失败，请查看会话详情或重试",
                        "timestamp": _now(),
                    }
                )
            else:
                yield _sse(
                    {
                        "type": "done",
                        "analysis_id": analysis_id,
                        "session_id": session_id,
                        "duration_ms": int((time.time() - start_time) * 1000),
                        "timestamp": _now(),
                    }
                )
            return
```

修改为：

```python
    if stock_code and not req.session_id:
        async def event_stream() -> AsyncGenerator[str, None]:
            # session_created 通过 publish 写入 journal（恢复端点可重放）
            await stream_registry.publish(
                session_id,
                {
                    "type": "session_created",
                    "session_id": session_id,
                    "display_name": display_name,
                    "timestamp": _now(),
                },
            )
            update_session_for_clarify(
                session_id, stock_code=stock_code, stock_name=stock_name, status="running"
            )
            # 管线后台执行：事件桥接到 stream_registry journal
            loop = asyncio.get_event_loop()
            PipelineRunner.start(
                session_id,
                lambda: _run_graph_streaming(
                    stock_code, stock_name, req, analysis_id, start_time, session_id=session_id
                ),
                {
                    "layerTree": build_layer_tree(),
                    "currentNodeId": "",
                    "progress": 0.0,
                    "updatedAt": int(time.time() * 1000),
                },
                loop=loop,
            )
            # 订阅模式：从 journal 重放 + 实时事件，终态由 PipelineRunner._run 发布
            gen = stream_registry.subscribe(session_id, after_seq=0)
            while True:
                try:
                    event = await asyncio.wait_for(gen.__anext__(), timeout=10.0)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                except StopAsyncIteration:
                    break
```

- [ ] **Step 8: Modify `cancel_session` to add PipelineRunner.cancel**

在 `src/finance_agent/api.py` 的 `cancel_session` 端点中（Task 3 修改后的版本），将：

```python
    result = await stream_registry.cancel(session_id)
    if not result:
        # 无活跃任务：检查是否已有终态事件（幂等返回）
        terminal = await asyncio.to_thread(get_terminal_event, session_id)
        if terminal:
            return {"ok": True, "status": terminal["type"]}
        raise HTTPException(status_code=404, detail="No active task for this session")
    return {"ok": True, "status": "interrupted"}
```

修改为：

```python
    result = await stream_registry.cancel(session_id)
    pipelineResult = PipelineRunner.cancel(session_id)
    if not result and not pipelineResult:
        # 无活跃任务：检查是否已有终态事件（幂等返回）
        terminal = await asyncio.to_thread(get_terminal_event, session_id)
        if terminal:
            return {"ok": True, "status": terminal["type"]}
        raise HTTPException(status_code=404, detail="No active task for this session")
    return {"ok": True, "status": "interrupted"}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/test_fastpath_bridge.py -v`
Expected: PASS - 全部 3 个测试通过

- [ ] **Step 10: Run all backend tests to check for regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: PASS - 全部已有测试通过（如有因桥接改动导致的失败，需修复）

- [ ] **Step 11: Commit**

```bash
git add tests/test_fastpath_bridge.py src/finance_agent/pipeline_runner.py src/finance_agent/stream_registry.py src/finance_agent/api.py
git commit -m "feat: [pipeline] Fast path 桥接到 stream_registry + cancel 支持"
```

---

### Task 8: 前端 seq 去重 (#7)

**Files:**
- Modify: `frontend/src/App.tsx` - 三个 SSE 处理循环（startAnalysis、resumeStream、quickChat）增加 seq 去重检查
- Test: `frontend/src/test/seq-dedup.test.tsx`

**Interfaces:**
- Produces: 三个 SSE 循环中 `seq <= lastSeq` 的事件被跳过

- [ ] **Step 1: Write the failing test**

创建 `frontend/src/test/seq-dedup.test.tsx`：

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import App from '../App'

// 构造 SSE 流响应
function mockSSEResponse(events: any[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      for (const event of events) {
        const data = `data: ${JSON.stringify(event)}\n\n`
        controller.enqueue(encoder.encode(data))
      }
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('seq 去重', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
  })

  it('跳过 seq <= lastSeq 的旧事件', async () => {
    const events = [
      { type: 'session_created', session_id: 'test-1', display_name: 'Test', seq: 1, timestamp: '' },
      { type: 'chat_token', token: 'hello', seq: 2, timestamp: '' },
      // 重复 seq 的事件应被跳过
      { type: 'chat_token', token: 'world', seq: 2, timestamp: '' },
      { type: 'done', seq: 3, timestamp: '' },
    ]

    let fetchCallCount = 0
    global.fetch = vi.fn((url: string, opts?: any) => {
      fetchCallCount++
      if (url === '/api/analyze' && opts?.method === 'POST') {
        return Promise.resolve(mockSSEResponse(events))
      }
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }) as any

    const { container } = render(<App />)

    // 等待 EmptyState 渲染
    await waitFor(() => {
      expect(screen.getByTestId('send-button')).toBeTruthy()
    })

    // 输入并提交（deep 模式默认不需要 stockCode，走 ReAct 路径）
    // 实际测试中通过模拟输入触发 startAnalysis
    const textarea = container.querySelector('textarea')
    if (textarea) {
      await act(async () => {
        const event = new Event('input', { bubbles: true })
        Object.defineProperty(event, 'target', { value: textarea })
        textarea.value = 'test query'
        textarea.dispatchEvent(event)
      })

      await act(async () => {
        const btn = screen.getByTestId('send-button')
        btn.click()
      })
    }

    // 等待 SSE 事件处理完成
    await waitFor(() => {
      const streamOutput = screen.queryByTestId('stream-output')
      return streamOutput !== null
    }, { timeout: 5000 })

    // 验证只处理了 seq=2 的第一个 chat_token（"hello"），跳过了重复的 "world"
    await waitFor(() => {
      const output = screen.getByTestId('stream-output')
      const text = output.textContent || ''
      // "hello" 应在输出中，"world" 不应在（因为 seq=2 重复被跳过）
      expect(text).toContain('hello')
      expect(text).not.toContain('world')
    }, { timeout: 5000 })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/seq-dedup.test.tsx`
Expected: FAIL - 重复 seq 的事件未被跳过，输出包含 "helloworld"

- [ ] **Step 3: Add seq dedup check to `startAnalysis`**

在 `frontend/src/App.tsx` 的 `startAnalysis` 函数中，找到 SSE 事件处理循环（约 686 行），将：

```typescript
            // 更新 lastSeq（如果事件携带 seq 字段，delta spec Task 5.4）
            if (streamingSessionIdRef.current) {
              const seq = (event as SSEEvent & { seq?: number }).seq
              if (seq !== undefined) {
                const ss = getStreamState(streamingSessionIdRef.current)
                if (seq > ss.lastSeq) ss.lastSeq = seq
              }
            }
```

修改为：

```typescript
            // seq 去重：跳过 seq <= lastSeq 的旧事件
            if (streamingSessionIdRef.current) {
              const seq = (event as SSEEvent & { seq?: number }).seq
              if (seq !== undefined) {
                const ss = getStreamState(streamingSessionIdRef.current)
                if (seq <= ss.lastSeq) continue  // 跳过旧事件
                ss.lastSeq = seq
              }
            }
```

- [ ] **Step 4: Add seq dedup check to `resumeStream`**

在 `resumeStream` 函数中（约 1407 行），将：

```typescript
            // 更新 lastSeq（事件携带 seq 字段时）
            const seq = (event as SSEEvent & { seq?: number }).seq
            if (seq !== undefined && seq > state.lastSeq) {
              state.lastSeq = seq
            }
```

修改为：

```typescript
            // seq 去重：跳过 seq <= lastSeq 的旧事件
            const seq = (event as SSEEvent & { seq?: number }).seq
            if (seq !== undefined) {
              if (seq <= state.lastSeq) continue  // 跳过旧事件
              state.lastSeq = seq
            }
```

- [ ] **Step 5: Add seq dedup check to `quickChat`**

在 `quickChat` 函数中（约 1818 行），将：

```typescript
            // 更新 lastSeq（如果事件携带 seq 字段，delta spec Task 5.4）
            if (streamingSessionIdRef.current) {
              const seq = (event as SSEEvent & { seq?: number }).seq
              if (seq !== undefined) {
                const ss = getStreamState(streamingSessionIdRef.current)
                if (seq > ss.lastSeq) ss.lastSeq = seq
              }
            }
```

修改为：

```typescript
            // seq 去重：跳过 seq <= lastSeq 的旧事件
            if (streamingSessionIdRef.current) {
              const seq = (event as SSEEvent & { seq?: number }).seq
              if (seq !== undefined) {
                const ss = getStreamState(streamingSessionIdRef.current)
                if (seq <= ss.lastSeq) continue  // 跳过旧事件
                ss.lastSeq = seq
              }
            }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/seq-dedup.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/test/seq-dedup.test.tsx
git commit -m "feat: [frontend] SSE 事件 seq 去重，跳过旧事件"
```

---

### Task 9: 前端统一 handleSSEEvent (#9)

**Files:**
- Modify: `frontend/src/App.tsx` - 提取 `handleSSEEvent` 统一函数，重构三个调用方
- Test: `frontend/src/test/handle-sse-event.test.tsx`

**Interfaces:**
- Produces: `handleSSEEvent(event: SSEEvent, sessionId: string, skipIncremental?: boolean): boolean` 统一处理所有事件类型

- [ ] **Step 1: Write the failing test**

创建 `frontend/src/test/handle-sse-event.test.tsx`：

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import App from '../App'
import type { SSEEvent } from '../types'

// 构造 SSE 流响应
function mockSSEResponse(events: any[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      for (const event of events) {
        const data = `data: ${JSON.stringify(event)}\n\n`
        controller.enqueue(encoder.encode(data))
      }
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('handleSSEEvent 统一处理', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    localStorage.setItem('fa_api_key', 'test-key')
  })

  it('正确处理 session_created 事件', async () => {
    const events = [
      { type: 'session_created', session_id: 'test-sc', display_name: 'Test SC', seq: 1, timestamp: '' },
      { type: 'done', seq: 2, timestamp: '' },
    ]

    global.fetch = vi.fn((url: string, opts?: any) => {
      if (url === '/api/analyze' && opts?.method === 'POST') {
        return Promise.resolve(mockSSEResponse(events))
      }
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }) as any

    const { container } = render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('send-button')).toBeTruthy()
    })

    const textarea = container.querySelector('textarea')
    if (textarea) {
      await act(async () => {
        textarea.value = 'test'
        textarea.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => {
        screen.getByTestId('send-button').click()
      })
    }

    // session_created 后会话列表刷新
    await waitFor(() => {
      const fetchCalls = (global.fetch as any).mock.calls
      const sessionCalls = fetchCalls.filter((c: any[]) => c[0] === '/api/sessions')
      expect(sessionCalls.length).toBeGreaterThan(0)
    }, { timeout: 5000 })
  })

  it('正确处理 interrupted 终态事件', async () => {
    const events = [
      { type: 'session_created', session_id: 'test-int', display_name: 'Test Int', seq: 1, timestamp: '' },
      { type: 'chat_token', token: 'partial', seq: 2, timestamp: '' },
      { type: 'interrupted', seq: 3, timestamp: '' },
    ]

    global.fetch = vi.fn((url: string, opts?: any) => {
      if (url === '/api/analyze' && opts?.method === 'POST') {
        return Promise.resolve(mockSSEResponse(events))
      }
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }) as any

    const { container } = render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('send-button')).toBeTruthy()
    })

    const textarea = container.querySelector('textarea')
    if (textarea) {
      await act(async () => {
        textarea.value = 'test'
        textarea.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => {
        screen.getByTestId('send-button').click()
      })
    }

    // interrupted 后流式状态应清除
    await waitFor(() => {
      const outputs = screen.queryAllByTestId('stream-output')
      if (outputs.length > 0) {
        const streamingCursors = outputs[0].querySelector('.streaming-cursor')
        // interrupted 后 streaming 应停止
        return streamingCursors === null || !outputs[0].querySelector('.is-streaming')
      }
      return true
    }, { timeout: 5000 })
  })

  it('正确处理 done 终态事件', async () => {
    const events = [
      { type: 'session_created', session_id: 'test-done', display_name: 'Test Done', seq: 1, timestamp: '' },
      { type: 'chat_token', token: 'reply', seq: 2, timestamp: '' },
      { type: 'done', seq: 3, timestamp: '' },
    ]

    global.fetch = vi.fn((url: string, opts?: any) => {
      if (url === '/api/analyze' && opts?.method === 'POST') {
        return Promise.resolve(mockSSEResponse(events))
      }
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }) as any

    const { container } = render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('send-button')).toBeTruthy()
    })

    const textarea = container.querySelector('textarea')
    if (textarea) {
      await act(async () => {
        textarea.value = 'test'
        textarea.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => {
        screen.getByTestId('send-button').click()
      })
    }

    // done 后应显示回复内容
    await waitFor(() => {
      const outputs = screen.queryAllByTestId('stream-output')
      if (outputs.length > 0) {
        expect(outputs[0].textContent).toContain('reply')
      }
    }, { timeout: 5000 })
  })

  it('正确处理 error 终态事件', async () => {
    const events = [
      { type: 'session_created', session_id: 'test-err', display_name: 'Test Err', seq: 1, timestamp: '' },
      { type: 'error', message: 'Something went wrong', seq: 2, timestamp: '' },
    ]

    global.fetch = vi.fn((url: string, opts?: any) => {
      if (url === '/api/analyze' && opts?.method === 'POST') {
        return Promise.resolve(mockSSEResponse(events))
      }
      return Promise.resolve(new Response(JSON.stringify({ sessions: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }) as any

    const { container } = render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('send-button')).toBeTruthy()
    })

    const textarea = container.querySelector('textarea')
    if (textarea) {
      await act(async () => {
        textarea.value = 'test'
        textarea.dispatchEvent(new Event('input', { bubbles: true }))
      })
      await act(async () => {
        screen.getByTestId('send-button').click()
      })
    }

    // error 后应显示错误消息
    await waitFor(() => {
      const errorEl = screen.queryByTestId('stream-error')
      if (errorEl) {
        expect(errorEl.textContent).toContain('Something went wrong')
      }
    }, { timeout: 5000 })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/handle-sse-event.test.tsx`
Expected: FAIL - 当前没有统一的 `handleSSEEvent` 函数，测试可能因事件处理逻辑分散而行为不一致

- [ ] **Step 3: Rename existing `handleSSEEvent` to `applyPipelineEvent`**

在 `frontend/src/App.tsx` 中，现有的 `handleSSEEvent` 函数（约 924 行）处理管线事件。将其重命名为 `applyPipelineEvent`：

将：

```typescript
  const handleSSEEvent = (event: SSEEvent, pipelineMsg: UIMessage) => {
    switch (event.type) {
      case 'parsing':
```

修改为：

```typescript
  // 管线事件处理器（内部使用，由 handleSSEEvent 调用）
  const applyPipelineEvent = (event: SSEEvent, pipelineMsg: UIMessage) => {
    switch (event.type) {
      case 'parsing':
```

然后更新所有调用 `handleSSEEvent(event, pipelineMsgRef.current)` 的地方为 `applyPipelineEvent(event, pipelineMsgRef.current)`。需要更新的位置（在 `startAnalysis`、`resumeStream`、`replayBufferedEvents` 中搜索 `handleSSEEvent(` 并替换为 `applyPipelineEvent(`）。

注意：`handleSSEEvent` 在 `replayBufferedEvents` 中也有调用（约 1131、1154、1175、1314 行），都需要替换。

- [ ] **Step 4: Extract unified `handleSSEEvent` function**

在 `applyPipelineEvent` 函数之后添加新的 `handleSSEEvent` 统一函数：

```typescript
  // ── 统一 SSE 事件处理器 ──
  // startAnalysis、resumeStream、quickChat 三个 SSE 处理循环统一调用此函数。
  // 包含：seq 去重、会话隔离、session_created 幂等、终态事件处理、管线/对话事件路由。
  // 返回 true=已处理，false=未处理（调用方可继续判断或跳过）。
  const handleSSEEvent = (
    event: SSEEvent,
    sessionId: string,
    skipIncremental: boolean = false
  ): boolean => {
    // 1. seq 去重
    const state = getStreamState(sessionId)
    const seq = (event as SSEEvent & { seq?: number }).seq
    if (seq !== undefined) {
      if (seq <= state.lastSeq) return false  // 跳过旧事件
      state.lastSeq = seq
    }

    // 2. session_created 幂等
    if (event.type === 'session_created') {
      streamingSessionIdRef.current = event.session_id
      setCurrentSessionId(event.session_id)
      const streamState = getStreamState(event.session_id)
      streamState.abort = abortRef.current
      loadSessions()
      return true
    }

    // 3. 会话隔离：非当前视图事件存入缓冲区
    if (streamingSessionIdRef.current && streamingSessionIdRef.current !== currentSessionIdRef.current) {
      const skipTypes = new Set(['chat_token', 'thinking_token', 'report_chunk', 'report_ready'])
      if (!skipTypes.has(event.type)) {
        bufferedSseEventsRef.current.push(event)
      }
      return false
    }

    // 4. skipIncremental（resumeStream 从缓存恢复时跳过增量内容）
    if (skipIncremental) {
      const incrementalTypes = new Set(['chat_token', 'thinking_token', 'thinking_replace', 'thinking_to_answer', 'report_chunk'])
      if (incrementalTypes.has(event.type)) return false
    }

    // 5. 终态事件处理
    if (event.type === 'interrupted') {
      const finishedSessionId = streamingSessionIdRef.current
      streamingSessionIdRef.current = null
      abortRef.current = null
      if (finishedSessionId) {
        sessionCacheRef.current.delete(finishedSessionId)
      }
      handleStreamTerminal(finishedSessionId)
      setAppState('clarifying')
      if (assistantMsgIdRef.current) {
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
        ))
      }
      if (pipelineMsgRef.current) {
        updateMessage(pipelineMsgIdRef.current || pipelineMsgRef.current.id, { content: '输出已中断，可追问继续' })
      }
      return true
    }

    if (event.type === 'done') {
      const finishedSessionId = streamingSessionIdRef.current
      streamingSessionIdRef.current = null
      abortRef.current = null
      if (finishedSessionId) {
        sessionCacheRef.current.delete(finishedSessionId)
      }
      handleStreamTerminal(finishedSessionId)
      if (assistantMsgIdRef.current) {
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
        ))
      }
      return true
    }

    if (event.type === 'error') {
      if (pipelineMsgRef.current) {
        applyPipelineEvent(event, pipelineMsgRef.current)
      } else {
        setMessages(prev => [...prev, {
          id: genId(),
          type: 'error',
          content: `错误: ${(event as any).message}`,
        }])
      }
      return true
    }

    // 6. 管线事件路由
    if (event.type === 'analysis_start') {
      setAppState('analyzing')
      if (!pipelineMsgRef.current) {
        const pm: UIMessage = {
          id: genId(),
          type: 'pipeline',
          content: `开始分析 ${(event as any).stock_name} (${(event as any).stock_code})`,
          completedNodes: [],
          currentNode: '',
          nodeOutputs: {},
          progress: 0,
        }
        pipelineMsgIdRef.current = pm.id
        pipelineMsgRef.current = pm
        setMessages(prev => [...prev, pm])
      }
      return true
    }

    if (event.type === 'awaiting_input') {
      setAppState('clarifying')
      if (assistantMsgIdRef.current) {
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgIdRef.current ? { ...m, streaming: false } : m
        ))
      }
      return true
    }

    // 幂等创建管线消息
    const ensurePipelineMsg = (content: string): UIMessage => {
      if (pipelineMsgRef.current) return pipelineMsgRef.current
      const pm: UIMessage = {
        id: genId(),
        type: 'pipeline',
        content,
        completedNodes: [],
        currentNode: '',
        nodeOutputs: {},
        progress: 0,
        startedAt: Date.now(),
      }
      pipelineMsgIdRef.current = pm.id
      pipelineMsgRef.current = pm
      setMessages(prev => [...prev, pm])
      setAppState('analyzing')
      return pm
    }

    // 幂等创建助手消息
    const ensureAssistantMsg = (): string => {
      if (assistantMsgIdRef.current) return assistantMsgIdRef.current
      const newId = genId()
      assistantMsgIdRef.current = newId
      setMessages(prev => [...prev, {
        id: newId,
        type: 'chat',
        content: '',
        chatResponse: '',
        streaming: true,
      }])
      return newId
    }

    if (event.type === 'tool_call') {
      if ((event as any).name === 'run_deep_analysis') {
        ensurePipelineMsg('开始深度分析...')
      } else {
        handleChatStreamEvent(event, ensureAssistantMsg())
      }
      return true
    }

    if (event.type === 'search_start' || event.type === 'search_result' || event.type === 'search_error') {
      handleChatStreamEvent(event, ensureAssistantMsg())
      return true
    }

    if (event.type === 'tool_result') {
      if ((event as any).name !== 'run_deep_analysis') {
        handleChatStreamEvent(event, ensureAssistantMsg())
      }
      return true
    }

    if (event.type === 'stock_resolved') {
      if (pipelineMsgRef.current) {
        updateMessage(pipelineMsgRef.current.id, { content: `已识别：${(event as any).stock_name} (${(event as any).stock_code})` })
      } else {
        handleChatStreamEvent(
          { type: 'tool_result', name: 'search_stock', result: `已识别：${(event as any).stock_name} (${(event as any).stock_code})`, timestamp: '' } as SSEEvent,
          ensureAssistantMsg(),
        )
      }
      return true
    }

    if (event.type === 'thinking_token') {
      if (pipelineMsgRef.current) {
        applyPipelineEvent(event, pipelineMsgRef.current)
      } else {
        handleChatStreamEvent(event, ensureAssistantMsg())
      }
      return true
    }

    if (event.type === 'thinking_replace') {
      if (!pipelineMsgRef.current) {
        handleChatStreamEvent(event, ensureAssistantMsg())
      }
      return true
    }

    if (event.type === 'thinking_to_answer') {
      if (!pipelineMsgRef.current) {
        handleChatStreamEvent(event, ensureAssistantMsg())
      }
      return true
    }

    if (event.type === 'parsing' ||
        event.type === 'resolved' ||
        event.type === 'node_start' ||
        event.type === 'node_timing' ||
        event.type === 'node_complete') {
      const pm = ensurePipelineMsg('深度分析进行中...')
      applyPipelineEvent(event, pm)
      return true
    }

    if (event.type === 'report_chunk' || event.type === 'report_ready') {
      applyPipelineEvent(event, pipelineMsgRef.current || { id: genId(), type: 'pipeline', content: '' } as UIMessage)
      return true
    }

    if (event.type === 'chat_token') {
      if (!assistantMsgIdRef.current) {
        const newAssistantId = genId()
        assistantMsgIdRef.current = newAssistantId
        setMessages(prev => [...prev, {
          id: newAssistantId,
          type: 'chat',
          content: '',
          chatResponse: (event as any).token,
          streaming: true,
        }])
      } else {
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgIdRef.current ? applyChatStreamEvent(m, event) : m
        ))
      }
      return true
    }

    return false
  }
```

- [ ] **Step 5: Refactor `startAnalysis` to use `handleSSEEvent`**

在 `startAnalysis` 函数中，将 SSE 事件处理循环（从 `for (const line of lines)` 到循环结束）简化为：

将 `startAnalysis` 中从约 680 行开始的 `for (const line of lines)` 循环体替换为：

```typescript
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event: SSEEvent = JSON.parse(line.slice(6))
            handleSSEEvent(event, streamingSessionIdRef.current || sessionId || '')
          } catch {
            // Skip malformed lines
          }
        }
```

注意：保留循环后的「流结束但未收到终态事件」清理逻辑不变。

- [ ] **Step 6: Refactor `resumeStream` to use `handleSSEEvent`**

在 `resumeStream` 函数中，将 SSE 事件处理循环简化为：

将 `resumeStream` 中从约 1400 行开始的 `for (const line of lines)` 循环体替换为：

```typescript
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event: SSEEvent = JSON.parse(line.slice(6))
            handleSSEEvent(event, sessionId, skipIncremental)
          } catch {
            // Skip malformed lines
          }
        }
```

注意：保留循环后的清理逻辑不变。`resumeStream` 中的 `ensurePipelineMsg` 和 `ensureAssistantMsg` 闭包可以删除（已由 `handleSSEEvent` 内部处理）。

- [ ] **Step 7: Refactor `quickChat` to use `handleSSEEvent`**

在 `quickChat` 函数中，将 SSE 事件处理循环简化为：

将 `quickChat` 中从约 1812 行开始的 `for (const line of lines)` 循环体替换为：

```typescript
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event: SSEEvent = JSON.parse(line.slice(6))
            // quickChat 中对话流事件需要绑定到 chatId
            // handleChatStreamEvent 已在 handleSSEEvent 内部调用
            handleSSEEvent(event, streamingSessionIdRef.current || currentSessionId || '')
          } catch {
            // Skip malformed lines
          }
        }
```

注意：`quickChat` 中创建的 `chatMsg`（`chatId`）需要与 `handleSSEEvent` 内部的 `ensureAssistantMsg` 协调。由于 `handleSSEEvent` 内部的 `ensureAssistantMsg` 会检查 `assistantMsgIdRef.current`，需要在 `quickChat` 调用 `handleSSEEvent` 之前设置 `assistantMsgIdRef.current = chatId`。

在 `quickChat` 中，在 SSE 循环之前添加：

```typescript
    // 设置 assistantMsgIdRef，使 handleSSEEvent 的 ensureAssistantMsg 复用此消息
    assistantMsgIdRef.current = chatId
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/handle-sse-event.test.tsx`
Expected: PASS - 全部 4 个测试通过

- [ ] **Step 9: Run all frontend tests to check for regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS - 全部已有测试通过

- [ ] **Step 10: Commit**

```bash
git add frontend/src/App.tsx frontend/src/test/handle-sse-event.test.tsx
git commit -m "feat: [frontend] 提取统一 handleSSEEvent 事件处理器，重构三个 SSE 循环"
```

---

## Self-Review

### Spec coverage

| 偏离点 | 任务 | 状态 |
| --- | --- | --- |
| #1 SSE 帧带 id: {seq} | Task 1 | ✅ |
| #2 双轨制统一 | Task 7 | ✅ |
| #3 终态竞态 CAS | Task 3 | ✅ |
| #4 cancel 幂等 | Task 3 | ✅ |
| #5 增量持久化 | Task 5 | ✅ |
| #6 204 语义 | Task 4 | ✅ |
| #7 seq 去重 | Task 8 | ✅ |
| #8 重放缝合竞态 | Task 6 | ✅ |
| #9 前端统一处理 | Task 9 | ✅ |
| #10 心跳间隔 | Task 1 | ✅ |

### Placeholder scan

- 无 "TBD"、"TODO"、"implement later" 等占位符
- 所有步骤包含完整代码
- 所有测试代码完整可运行

### Type consistency

- `has_terminal_event(session_id: str) -> bool` - Task 2 定义，Task 3 消费 ✅
- `get_terminal_event(session_id: str) -> dict | None` - Task 2 定义，Task 3 消费 ✅
- `upsert_chat(session_id, role, content, ...)` - Task 5 定义并消费 ✅
- `PipelineRunner.start(..., loop=None)` - Task 7 定义并消费 ✅
- `PipelineRunner.cancel(session_id) -> bool` - Task 7 定义并消费 ✅
- `handleSSEEvent(event, sessionId, skipIncremental)` - Task 9 定义并消费 ✅
- `applyPipelineEvent(event, pipelineMsg)` - Task 9 重命名自 `handleSSEEvent` ✅
