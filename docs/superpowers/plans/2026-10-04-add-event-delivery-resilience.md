# add-event-delivery-resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 事件发布链路设防——终态优先送达、积压背压可观测、SQLite 瞬态重试、空结果显式语义、超时判定基于图真实完成状态（delta `add-event-delivery-resilience`，incident 037 + 2026-10-04 20:39 拓荆误判超时案例）。

**Architecture:** 五处独立修改共享一个原则「完成事实的可靠性高于明细完整性」：`session_store._get_db` 连接层短重试（Task 1）；`StreamRegistry` 新增终态重试发布与丢弃计数（Task 2）；`agent_factory._background_consume` 分类背压 + 图完成信号 + 看门狗核对（Task 3，核心）；生产端收拢（pending 上限 + 终态统一走 publish_terminal，Task 4）；`harness/loop.py` 空 output 守卫（Task 5）。

**Tech Stack:** Python 3.12 / pytest / pytest-asyncio（asyncio_mode=auto）/ threading.Event / monkeypatch

## Global Constraints

- 工作目录：`.worktrees/event-delivery-resilience`（分支 `add-event-delivery-resilience`，基于 main `491ba22d`）。禁止在主检出切分支
- commit 格式：`feat(<scope>): <中文描述> (add-event-delivery-resilience)`；禁止 merge commit
- 每任务收尾 `uv run ruff check` 与 `uv run mypy src/finance_agent/<改动目录>` 必须绿（mypy 全仓基线 83 errors，不得新增）
- 测试不触网：SQLite 用 tmp_path 隔离（参照 `tests/test_db_isolation.py` 护栏）、monkeypatch 时间与 sleep
- 不改 `src/finance_agent/prompts/`；不改 `report.py`（036 范围）
- 注释风格：中文、说明契约来源（引用 delta 需求名）
- 禁止静默丢弃：任何事件丢弃路径 MUST 计数 + 日志（spec「发布积压可观测与背压」）
- 既有语义红线：seq 单调、先落库后 fan-out、慢订阅者断开、终态 per-run CAS、40 分钟默认预算——全部不得回退

---

### Task 1: session_store SQLite 瞬态重试

**Files:**
- Modify: `src/finance_agent/session_store.py:61-67`（`_get_db`）
- Test: `tests/test_session_store_retry.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `_get_db()` 行为变更（签名不变）——全部读写函数自动获得瞬态重试

- [ ] **Step 1: 写失败测试**

```python
# tests/test_session_store_retry.py
"""_get_db 瞬态错误重试（delta add-event-delivery-resilience spec session-persistence）。"""
import sqlite3

import pytest

from finance_agent import session_store as ss


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_DB_PATH", tmp_path / "sessions.db")
    return tmp_path / "sessions.db"


class TestGetDbTransientRetry:
    def test_unable_to_open_retries_then_succeeds(self, isolated_db, monkeypatch):
        """瞬断自愈窗口内：前 2 次 connect 抛 unable to open，第 3 次成功。"""
        calls = {"n": 0}
        real_connect = sqlite3.connect

        def flaky_connect(*a, **kw):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise sqlite3.OperationalError("unable to open database file")
            return real_connect(*a, **kw)

        monkeypatch.setattr(ss.sqlite3, "connect", flaky_connect)
        monkeypatch.setattr(ss.time, "sleep", lambda _s: None)
        conn = ss._get_db()
        assert calls["n"] == 3
        conn.close()

    def test_pragma_failure_also_retried(self, isolated_db, monkeypatch):
        """connect 成功但 PRAGMA 阶段瞬断，同样走重试（整块包裹）。"""

        class FlakyConn:
            def __init__(self, inner):
                self._inner = inner
                self._pragma_calls = 0

            def execute(self, sql, *a):
                self._pragma_calls += 1
                if sql.startswith("PRAGMA journal_mode") and self._pragma_calls == 1:
                    raise sqlite3.OperationalError("disk I/O error")
                return self._inner.execute(sql, *a)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        real_connect = sqlite3.connect
        state = {"n": 0}

        def connect_once_flaky(*a, **kw):
            state["n"] += 1
            inner = real_connect(*a, **kw)
            if state["n"] == 1:
                return FlakyConn(inner)
            return inner

        monkeypatch.setattr(ss.sqlite3, "connect", connect_once_flaky)
        monkeypatch.setattr(ss.time, "sleep", lambda _s: None)
        conn = ss._get_db()
        assert state["n"] == 2
        conn.close()

    def test_retry_exhausted_raises(self, isolated_db, monkeypatch):
        """瞬态错误持续超过重试窗口：显式 raise 原异常，不静默。"""
        monkeypatch.setattr(
            ss.sqlite3,
            "connect",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("unable to open database file")
            ),
        )
        monkeypatch.setattr(ss.time, "sleep", lambda _s: None)
        with pytest.raises(sqlite3.OperationalError):
            ss._get_db()

    def test_non_transient_error_not_retried(self, isolated_db, monkeypatch):
        """非瞬态错误（如 no such table）不重试，立即 raise。"""
        calls = {"n": 0}

        def bad_connect(*a, **kw):
            calls["n"] += 1
            raise sqlite3.OperationalError("no such table: something")

        monkeypatch.setattr(ss.sqlite3, "connect", bad_connect)
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            ss._get_db()
        assert calls["n"] == 1
```

注意：`ss.time` 要求 session_store 顶部 `import time`（若模块未导入则补 import 并在测试中 monkeypatch `ss.time.sleep`）；`ss.sqlite3` 同理确认可 monkeypatch 属性（sqlite3 是模块对象，直接 setattr 其 `connect` 会污染全局——改用 `monkeypatch.setattr(ss, "sqlite3", sqlite3)` 不行，因为模块对象共享。**正确做法**：`_get_db` 内改为调用模块级包装 `ss.sqlite3.connect`，测试用 `monkeypatch.setattr("sqlite3.connect", flaky_connect)`（pytest 自动还原），`sleep` 用 `monkeypatch.setattr("time.sleep", ...)`。上面测试代码已按此写法。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_session_store_retry.py -v`
Expected: FAIL（`_get_db` 无重试，第一次 OperationalError 直接抛出）

- [ ] **Step 3: 最小实现**

```python
# session_store.py 顶部常量区（_EVENT_APPEND_* 附近）
# 瞬态 SQLite 错误模式（delta add-event-delivery-resilience spec「SQLite 瞬态错误重试」）：
# unable to open database file = bind mount 瞬断；locked = busy_timeout 覆盖不到的
# 连接期锁；disk I/O error = 存储瞬态。非瞬态错误不重试立即抛出。
_DB_TRANSIENT_PATTERNS = ("unable to open database file", "database is locked", "disk i/o error")
_DB_CONNECT_MAX_RETRIES = 4
_DB_CONNECT_RETRY_BASE_SLEEP = 0.1


def _get_db() -> sqlite3.Connection:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(_DB_CONNECT_MAX_RETRIES):
        try:
            conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            # 并发写等待锁而非立即抛 "database is locked"（流式 token 高频落库场景必需）
            conn.execute("PRAGMA busy_timeout=15000")
            return conn
        except sqlite3.OperationalError as exc:
            if not any(p in str(exc).lower() for p in _DB_TRANSIENT_PATTERNS):
                raise
            last_exc = exc
            time.sleep(_DB_CONNECT_RETRY_BASE_SLEEP * (2**attempt))
    raise last_exc  # type: ignore[misc]
```

（session_store 若无 `import time` 则补。）

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_session_store_retry.py tests/test_session_store.py tests/test_session_events.py -q`
Expected: PASS（新 4 用例 + 存量全绿）

- [ ] **Step 5: Lint + 类型 + Commit**

```bash
uv run ruff check src/finance_agent/session_store.py tests/test_session_store_retry.py
uv run mypy src/finance_agent/session_store.py
git add src/finance_agent/session_store.py tests/test_session_store_retry.py
git commit -m "fix(store): _get_db 瞬态错误短重试——unable to open/locked/I/O error 覆盖全部读写 (add-event-delivery-resilience)"
```

---

### Task 2: StreamRegistry 终态重试发布 + 丢弃计数

**Files:**
- Modify: `src/finance_agent/stream_registry.py`（`publish` 后新增 `publish_terminal`；`__init__` 加计数结构；`_fanout` 附近的丢弃计数挂点）
- Test: `tests/test_stream_registry_terminal_priority.py`（新建）

**Interfaces:**
- Consumes: `session_store.append_session_event`（既有）
- Produces:
  - `async def publish_terminal(self, session_id: str, event: dict) -> int` — 终态专用发布：per-run CAS → journal 重试写（5 次 × 1s）→ fan-out；返回 seq（CAS 拒绝返回 0）；重试耗尽 raise
  - `def record_drop(self, session_id: str, kind: str) -> None` — 明细丢弃计数（线程安全：仅事件循环内调用）
  - `def backlog_stats(self, session_id: str) -> dict` — 返回 `{"drops": {kind: n}, "subscribers": int, "last_seq": int}`；无 stream 返回 `{"drops": {}, "subscribers": 0, "last_seq": 0}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_stream_registry_terminal_priority.py
"""publish_terminal 重试发布 + record_drop/backlog_stats（spec session-streaming）。"""
import asyncio

import pytest

from finance_agent import session_store as ss
from finance_agent.stream_registry import StreamRegistry


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_DB_PATH", tmp_path / "sessions.db")
    ss.init_db()


@pytest.fixture
def registry():
    return StreamRegistry()


def _make_subscriber(registry, session_id, maxlen=256):
    q: asyncio.Queue = asyncio.Queue(maxlen=maxlen)
    stream = registry._streams.setdefault(session_id, __import__(
        "finance_agent.stream_registry", fromlist=["SessionStream"]
    ).SessionStream())
    stream.subscribers.append(q)
    return q


@pytest.mark.asyncio
async def test_publish_terminal_journals_and_fans_out(isolated_db, registry):
    sid = "s-term-1"
    q = _make_subscriber(registry, sid)
    seq = await registry.publish_terminal(sid, {"type": "done"})
    assert seq >= 1
    assert q.qsize() == 1
    assert q.get_nowait()["type"] == "done"
    rows = ss.list_session_events(sid)
    assert rows[-1]["seq"] == seq


@pytest.mark.asyncio
async def test_publish_terminal_cas_dedup(isolated_db, registry):
    sid = "s-term-2"
    _make_subscriber(registry, sid)
    first = await registry.publish_terminal(sid, {"type": "done"})
    second = await registry.publish_terminal(sid, {"type": "done"})
    assert first >= 1 and second == 0


@pytest.mark.asyncio
async def test_publish_terminal_retries_then_succeeds(isolated_db, registry, monkeypatch):
    sid = "s-term-3"
    _make_subscriber(registry, sid)
    calls = {"n": 0}
    real = ss.append_session_event

    def flaky(sid_, ev):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("transient journal failure")
        return real(sid_, ev)

    monkeypatch.setattr(ss, "append_session_event", flaky)
    sleeps: list[float] = []
    monkeypatch.setattr(asyncio, "sleep", lambda s: sleeps.append(s) or asyncio.sleep(0))
    seq = await registry.publish_terminal(sid, {"type": "error", "message": "x"})
    assert seq >= 1 and calls["n"] == 3 and len(sleeps) == 2


@pytest.mark.asyncio
async def test_publish_terminal_exhaustion_raises(isolated_db, registry, monkeypatch):
    sid = "s-term-4"
    _make_subscriber(registry, sid)
    monkeypatch.setattr(
        ss,
        "append_session_event",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("journal down")),
    )
    monkeypatch.setattr(asyncio, "sleep", lambda s: asyncio.sleep(0))
    with pytest.raises(RuntimeError):
        await registry.publish_terminal(sid, {"type": "done"})


def test_record_drop_and_backlog_stats(registry):
    sid = "s-drop-1"
    registry.record_drop(sid, "thinking")
    registry.record_drop(sid, "thinking")
    registry.record_drop(sid, "chunk")
    stats = registry.backlog_stats(sid)
    assert stats["drops"] == {"thinking": 2, "chunk": 1}
    assert stats["subscribers"] == 0
```

（`_make_subscriber` 直接操纵 `_streams` 是既有测试的模式——先读 `tests/test_stream_registry.py` / `tests/test_terminal_cas.py` 的现有 fixture 写法，若已有等价 helper 则复用其模式；此处给出的是自足版本。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_stream_registry_terminal_priority.py -v`
Expected: FAIL（`publish_terminal` / `record_drop` / `backlog_stats` 不存在）

- [ ] **Step 3: 最小实现**

```python
# stream_registry.py __init__
def __init__(self) -> None:
    self._streams: dict[str, SessionStream] = {}
    # 明细丢弃计数（spec「发布积压可观测与背压」：无计数无日志的静默丢弃 MUST NOT 存在）
    self._drop_counts: dict[str, dict[str, int]] = {}

def record_drop(self, session_id: str, kind: str) -> None:
    """明细事件丢弃计数（仅事件循环内调用，无锁）。"""
    per = self._drop_counts.setdefault(session_id, {})
    per[kind] = per.get(kind, 0) + 1

def backlog_stats(self, session_id: str) -> dict:
    """积压可观测快照：丢弃计数 / 订阅者数 / 最后 seq。"""
    stream = self._streams.get(session_id)
    return {
        "drops": dict(self._drop_counts.get(session_id, {})),
        "subscribers": len(stream.subscribers) if stream else 0,
        "last_seq": stream.lastSeq if stream else 0,
    }

async def publish_terminal(self, session_id: str, event: dict) -> int:
    """终态专用发布（spec「终态事件优先送达」）：CAS 去重 → journal 重试写 → fan-out。

    终态落库值得比普通写更固执：5 次 × 1s 重试（_get_db 层短重试之上的
    调用侧兜底）。重试耗尽 raise（显式失败，由调用方日志兜底），
    MUST NOT 静默吞掉造成「管线完成但终态缺失」。
    """
    if not self._try_mark_terminal(session_id, event):
        return 0
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            seq = await asyncio.to_thread(session_store.append_session_event, session_id, event)
            break
        except Exception as exc:  # noqa: BLE001 - journal 瞬断重试（终态关键路径）
            last_exc = exc
            _logger.warning(
                "终态落库重试 attempt=%s session=%s err=%s", attempt + 1, session_id, exc
            )
            await asyncio.sleep(1.0)
    else:
        raise last_exc  # type: ignore[misc]
    event["seq"] = seq
    stream = self._streams.get(session_id)
    if stream:
        stream.lastSeq = seq
        self._fanout(session_id, stream, event)
    return seq
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_stream_registry_terminal_priority.py tests/test_stream_registry.py tests/test_terminal_cas.py -q`
Expected: PASS

- [ ] **Step 5: Lint + 类型 + Commit**

```bash
uv run ruff check src/finance_agent/stream_registry.py tests/test_stream_registry_terminal_priority.py
uv run mypy src/finance_agent/stream_registry.py
git add src/finance_agent/stream_registry.py tests/test_stream_registry_terminal_priority.py
git commit -m "feat(stream): publish_terminal 终态重试发布 + 丢弃计数/backlog_stats 可观测 (add-event-delivery-resilience)"
```

---

### Task 3: 消费端分类背压 + 图完成信号 + 看门狗核对（核心）

**Files:**
- Modify: `src/finance_agent/agent_factory.py:549-643`（`_run_graph` / `event_queue` / `_background_consume` 头部与 `_put_event`）
- Test: `tests/test_pipeline_watchdog_graph_done.py`（新建）

**Interfaces:**
- Consumes: `StreamRegistry.record_drop`（Task 2）
- Produces: 行为契约——(a) thinking_token 队列满可丢弃且计数+节流日志；(b) 边界/工具/终态事件阻塞入队（有界 30s，超时计数+错误日志）；(c) `graph_done` 置位后 thinking 明细直接压缩丢弃（不入 event_queue、不累积 timeline）；(d) 预算耗尽且 `graph_done` 置位 → 不抛 TimeoutError，改用无超时 `get()` 排空至哨兵；(e) 预算耗尽且图未完成 → 维持 TimeoutError

**实现要点（先读 `agent_factory.py:544-640` 与 `tests/test_pipeline_timeout.py` 的现有测试 harness，再动手）：**

1. `_run_graph` 的 `finally` 中、`chunk_queue.put(None)` 之前，加 `graph_done.set()`（`graph_done = threading.Event()` 与 `graph_cancel` 同处声明）。
2. `_put_event` 改为 async 闭包（原同步版删除）：

```python
_thinking_dropped = 0

async def _put_event(evt, *, droppable: bool = False) -> None:
    """事件入队（spec「发布积压可观测与背压」分级处置）。

    droppable（thinking_token 明细）：队列满即丢弃，计数 + 节流日志。
    其余（节点边界/工具/终态）：阻塞入队不丢弃；下游消费者消失时
    30s 有界等待后放弃并显式日志——宁可显式放弃不可无限阻塞泄漏任务。
    """
    nonlocal _thinking_dropped
    if droppable and event_queue.full():
        _thinking_dropped += 1
        registry.record_drop(session_id or "", "thinking")
        if _thinking_dropped == 1 or _thinking_dropped % 100 == 0:
            _logger.warning(
                "thinking 明细丢弃（队列满）session=%s 累计=%s", session_id, _thinking_dropped
            )
        return
    try:
        await asyncio.wait_for(event_queue.put(evt), timeout=30.0)
    except asyncio.TimeoutError:
        registry.record_drop(session_id or "", "undeliverable")
        _logger.error("事件入队超时（消费者停滞）session=%s type=%s", session_id, evt)
```

3. 消费循环头部改：

```python
if not graph_done.is_set():
    # 墙钟超时（spec pipeline-events「管线超时与中断检测」MODIFIED：预算耗尽
    # 须先核对图完成信号——图已完成时排空延迟不构成超时，20:39 拓荆案例）
    _remaining = pipeline_timeout - (_time_module.time() - _pipeline_start_time)
    if _remaining <= 0:
        raise TimeoutError(f"管线执行超过 {pipeline_timeout}s 全局预算")
    item = await asyncio.wait_for(chunk_queue.get(), timeout=_remaining)
else:
    # 图已完成：排空剩余缓冲。thinking 明细在下方压缩丢弃，纯 CPU 速度排空
    item = await chunk_queue.get()
```

4. custom/thinking 分支内，`graph_done.is_set()` 时压缩：

```python
if ctype == "thinking":
    if graph_done.is_set():
        # spec「图完成后工具消费端压缩缓冲明细」：图完成后的思考明细
        # 是报告产出后的噪声，压缩丢弃使终态 TOOL_RESULT 有界送达
        registry.record_drop(session_id or "", "tail_thinking")
        continue
    ...（原 timeline 累积 + _put_event(StreamEvent.think(...), droppable=True)）
```

5. 其余 `_put_event(...)` 调用点全部加 `await`（progress/tool_result/终态 TOOL_RESULT/sentinel `None`）。sentinel 保持显式：`await _put_event(None)`（非 droppable，走 30s 有界等待）。

- [ ] **Step 1: 写失败测试**（harness 对齐 `tests/test_pipeline_timeout.py` 现有写法——先读该文件，复用其 monkeypatch 模式；核心场景如下，断言全部行为化）

场景 A「图完成+排空滞后不误判超时」：`PIPELINE_TIMEOUT_SECONDS` monkeypatch 为极小值；伪造图流：先产出 N 条 thinking chunk，然后结束（触发 `_run_graph` finally：`graph_done.set()` + 哨兵）。在消费侧注入延迟使预算在排空中途耗尽（monkeypatch `_time_module.time` 返回递增序列越过预算线）。断言：run_deep_analysis 最终 TOOL_RESULT 的 output **以「深度分析完成」开头**（正常完成路径）、metadata 含 `sse_type: report_ready`、**不含** `pipeline_timeout`；会话状态未被置 failed。

场景 B「图未完成预算耗尽仍判超时」：伪造图流持续产出 thinking chunk 不结束；预算耗尽。断言：TOOL_RESULT output 含「管线执行超时」、metadata `pipeline_timeout: True`、会话置 failed + `failure_reason=管线执行超时`。

场景 C「队列满时明细丢弃可观测」：event_queue maxsize 塞满且消费者暂停；继续产 thinking → `registry.backlog_stats(sid)["drops"]["thinking"] >= 1` 且日志有 WARNING；随后产 node_complete 类事件 → 不被丢弃（最终出现在事件流中）。

场景 D「图完成后 thinking 压缩」：图完成后仍有多条 thinking chunk 入 chunk_queue → 它们不出现在 run_deep_analysis 产出的事件流中，`backlog_stats` 的 `tail_thinking` 计数 = 条数；终态 TOOL_RESULT 在有界时间内（无逐条 journal 写延迟）产出。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_pipeline_watchdog_graph_done.py -v`
Expected: 场景 A FAIL（现实现抛 TimeoutError）、场景 C/D FAIL（无丢弃计数）；场景 B PASS（现状行为，作回归锚）

- [ ] **Step 3: 按「实现要点」改造 `_background_consume`**

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_pipeline_watchdog_graph_done.py tests/test_pipeline_timeout.py tests/test_deep_analysis_tool.py tests/test_react_loop.py tests/test_pipeline_write_blocking.py -q`
Expected: PASS（新 4 场景 + 存量回归全绿）

- [ ] **Step 5: Lint + 类型 + Commit**

```bash
uv run ruff check src/finance_agent/agent_factory.py tests/test_pipeline_watchdog_graph_done.py
uv run mypy src/finance_agent/agent_factory.py
git add src/finance_agent/agent_factory.py tests/test_pipeline_watchdog_graph_done.py
git commit -m "feat(react): 消费端分类背压+图完成信号——看门狗核对真实完成状态, 洪峰排空不误判超时 (add-event-delivery-resilience)"
```

---

### Task 4: 生产端收拢——终态统一 publish_terminal + pending 缓冲上限

**Files:**
- Modify: `src/finance_agent/pipeline_runner.py:342-351`（pending 上限）、`pipeline_runner.py:361-488`（interrupted/error/done 分支改 publish_terminal）、`src/finance_agent/api.py:1627-1720`（`_flush_tokens` 后终态、`_run_react_analysis` done 分支）
- Test: `tests/test_terminal_publish_unified.py`（新建）

**Interfaces:**
- Consumes: `StreamRegistry.publish_terminal`（Task 2）
- Produces: 行为契约——所有终态事件（done/error/interrupted/report_ready 视同终态关键路径）发布前 MUST 先冲刷本生产者的 pending 明细缓冲（保 seq 单调），发布 MUST 走 `publish_terminal`（重试兜底）；pending 明细缓冲超过 512 条丢最旧 thinking 并计数

- [ ] **Step 1: 写失败测试**

场景 A「fast path 终态走重试发布」：monkeypatch `PipelineRunner` 用的 registry 实例方法 `publish_terminal` 为 spy（内部转调真实现），触发一次正常完成的 fast path run（复用 `tests/test_pipeline_runner.py` 的现有 fake graph 模式），断言 `publish_terminal` 被调用且 `publish`（普通版）未被用于 done/error/interrupted。

场景 B「pending 超限丢最旧」：构造 pending 列表 > 512 条 thinking（直接调 `_flush_pending` 前的状态注入或抽出的纯函数），断言丢弃计数递增 + 队列长度守恒到上限。

场景 C「ReAct done 走 publish_terminal」：同场景 A 模式，针对 `api._run_react_analysis` 的 done 发布（复用 `tests/test_react_background.py` harness）。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_terminal_publish_unified.py -v`
Expected: FAIL（现状走 `registry.publish`，无 pending 上限）

- [ ] **Step 3: 实现**

1. `pipeline_runner.py` pending 处（:342-351 附近）：flush 前检查 `len(pending) > 512` → 丢最旧（`pending = pending[-512:]`）+ `registry.record_drop(session_id, "pending_overflow")` + `_logger.warning`（节流同 Task 3）。
2. `pipeline_runner.py` 三处终态（cancel :361-371 / timeout :373-391 / exception :453-471 / finally done :483-488）与 `api.py` 的 done/error 发布点（:1711-1733、`_flush_tokens` 后的终态）：先 `_flush_pending()`（或 `_flush_tokens()`），再 `await registry.publish_terminal(session_id, ev)` 替换原 `registry.publish`。CAS 拒绝（返回 0）静默容忍（与现 publish 语义一致）。
3. 注意 `_publish_sync`（CancelledError 路径）保持不变（不可 await 场景）。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_terminal_publish_unified.py tests/test_pipeline_runner.py tests/test_react_background.py tests/test_api_pipeline_resume.py tests/test_terminal_cas.py tests/test_followup_sse_termination.py -q`
Expected: PASS

- [ ] **Step 5: Lint + 类型 + Commit**

```bash
uv run ruff check src/finance_agent/pipeline_runner.py src/finance_agent/api.py tests/test_terminal_publish_unified.py
uv run mypy src/finance_agent/pipeline_runner.py src/finance_agent/api.py
git add src/finance_agent/pipeline_runner.py src/finance_agent/api.py tests/test_terminal_publish_unified.py
git commit -m "feat(pipeline): 终态统一走 publish_terminal + pending 缓冲上限——完成事实不与明细队列竞争 (add-event-delivery-resilience)"
```

---

### Task 5: harness 空 output 守卫

**Files:**
- Modify: `src/finance_agent/harness/loop.py:592-598`（缺失兜底处扩展空串分支）
- Test: `tests/test_react_loop.py` 追加用例（或新建 `tests/test_react_empty_tool_result.py`）

**Interfaces:**
- Consumes: 无
- Produces: 行为契约——streaming 工具 TOOL_RESULT output 为空串/纯空白时按工具失败处理（`is_error=True`、output=`[错误] 流式工具返回空结果`），`analysis_completed` 不置位

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_react_loop.py（或独立文件，跟随该文件现有 fixture 构造 loop）
async def test_empty_tool_output_treated_as_error(...):
    # 构造 streaming 工具 yield 一个 TOOL_RESULT 且 tool_result.output == ""
    # （复用该文件现有 fake streaming tool 模式）
    ...
    assert result.is_error is True
    assert "空结果" in result.output
    # analysis_completed 不置位：下一轮不进入强制摘要（可通过 loop 状态或后续行为断言）
```

（fixture 构造以 `tests/test_react_loop.py` 现有模式为准——先读后写，断言行为三要素：is_error=True、output 含「空结果」、analysis_completed 未置位。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_react_loop.py -k empty -v`
Expected: FAIL（现状空 output 不作失败处理）

- [ ] **Step 3: 最小实现**

```python
# loop.py :592 处，缺失兜底后追加空串分支
if result is None:
    result = ToolResult(
        tool_call_id=tc.id,
        name=tc.name,
        output="[错误] 流式工具未返回结果",
        is_error=True,
    )
elif not (result.output or "").strip():
    # delta add-event-delivery-resilience spec「管线异常终止的工具结果显式错误语义」：
    # 空串结果与缺失等价——MUST NOT 让摘要 LLM 拿到空输入自由发挥
    #（incident 037：「本次未返回有效报告内容」的空结果歧义）
    result = ToolResult(
        tool_call_id=tc.id,
        name=tc.name,
        output="[错误] 流式工具返回空结果",
        is_error=True,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_react_loop.py tests/test_agent_factory_blocked_terminal.py -q`
Expected: PASS（`:610` 的 `not result.is_error` 判定自动使 analysis_completed 不置位）

- [ ] **Step 5: Lint + 类型 + Commit**

```bash
uv run ruff check src/finance_agent/harness/loop.py
uv run mypy src/finance_agent/harness/loop.py
git add src/finance_agent/harness/loop.py tests/test_react_loop.py
git commit -m "fix(harness): 流式工具空 output 按失败处理——空结果歧义不进摘要上下文 (add-event-delivery-resilience)"
```

---

### Task 6: 全量验证（verification-before-completion）

**Files:** 无新改动（纯验证）

- [ ] **Step 1: 定向回归**

Run: `uv run pytest tests/test_stream_registry.py tests/test_terminal_cas.py tests/test_session_events_batch.py tests/test_pipeline_write_blocking.py tests/test_deep_analysis_tool.py tests/test_api_blocked_terminal.py tests/test_subscribe_order.py tests/test_event_seq_concurrency.py -q`
Expected: 全绿（seq 单调 / 先落库后 fan-out / CAS / 慢订阅者 / 批量 journal 不回退）

- [ ] **Step 2: 全量 + Lint + 类型**

Run: `uv run pytest -q -m "not live" --ignore=tests/e2e --ignore=tests/scripts` 然后 `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/` 然后 `uv run mypy src/ 2>&1 | tail -1`（与 main 基线 83 errors 对比，不得新增）
Expected: 0 failed（live 除外）/ ruff 双绿 / mypy 持平

- [ ] **Step 3: 汇报**

汇报真实输出（通过数/失败数/mypy 对比基线）。人工验证（真实深度分析 + 故障注入三界面归一）+ PR + 部署由主会话执行，不在本计划范围。
