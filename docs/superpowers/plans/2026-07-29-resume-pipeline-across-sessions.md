# resume-pipeline-across-sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 切换会话时深度分析管线在后端后台继续执行，切回会话时恢复管线 UI（运行中恢复时间轴并轮询进度，已完成恢复报告+静态时间轴）。

**Architecture:** 管线执行与 SSE 订阅解耦——新增 `PipelineRunner` 把 `graph.stream` 放到独立后台线程执行，每节点完成时持久化 layerTree 快照到 sessions 表新列 `pipeline_snapshot`；SSE 仅从内存事件队列订阅推送，断开不影响管线。前端 `selectSession` 按会话 status 分发恢复，running 会话每 2s 轮询快照。

**Tech Stack:** FastAPI + LangGraph（同步 `graph.stream`）、SQLite（session_store）、React 18 + TS + Vitest、pytest。

**Spec:** `openspec/changes/resume-pipeline-across-sessions/`（proposal.md / design.md / specs/ / tasks.md）

## Global Constraints

- TDD 红线：先写失败测试，再实现（AGENTS.md / project_rules.md）。
- 后端命名遵守项目既有风格（snake_case）；前端变量 camelCase（用户规则）。
- 代码注释使用中文。
- 测试产物位置：单测 fixtures → `tests/fixtures/`，人工验证报告 → `tests/validation/resume-pipeline-across-sessions-validation.md`；禁止根目录新建目录。
- E2E 禁止 mock 被测系统；LLM 可用 `TESTING=1` stub。
- 后端测试命令 `uv run pytest <path> -v`；前端测试 `cd frontend && npm test -- <path>`；Lint `uv run ruff check`；前端类型 `cd frontend && npx tsc --noEmit`。

## 现状关键事实（勘察结论）

- `graph.stream` 是**同步**生成器，在 SSE 路径中经 `_stream_from_sync`（`api.py:164` 附近，threadpool executor 迭代）被消费；客户端断开时 `event_stream` 被取消，executor 中的迭代也随之停止（fast path `api.py:924` 与 ReAct 工具路径 `agent_factory.stream_agent_to_sse` 均如此）。因此 D1「后台化」是必须项，不是可选优化。
- `_run_graph_streaming`（`api.py:559`）是同步生成器，yield SSE 字符串；节点事件（`node_start`/`node_complete`/`node_timing`）、`report_ready`、`error` 均在此产生；完成时 `update_session_report(..., status="completed")`（`api.py:747`），异常时 `update_session_status(session_id, "failed")`（`api.py:777`）。
- `session_store.init_db()` 用 `ALTER TABLE ... ADD COLUMN` + `contextlib.suppress(sqlite3.OperationalError)` 做幂等迁移（`session_store.py:79-85`），新列按同模式添加。
- `get_session`（`session_store.py:337`）`SELECT *`，新列自动返回。
- 前端 `selectSession`（`App.tsx:120`）目前无条件 `abortStreaming()` + `pipelineMsgRef.current = null`，只恢复 report + chat_history。
- 前端 `applyNodeEvent(tree, event, nowMs)`（`pipelineTree.ts:136`）是纯函数，接受 `node_start|node_complete|node_timing` 事件；`buildLayerTree()` 构建初始树；`UIMessage.layerTree` 字段已存在。
- 后端 `_NODE_MAP` / `_ALL_NODES` / `LAYER_STEPS` 在 `api.py` 顶层，节点 id 与前端 `LAYER_TREE_CONFIG` 一一对应。

## 快照契约（跨端共享，任务间接口）

```json
{
  "layerTree": [
    {
      "id": "prep",
      "label": "PREP",
      "status": "completed",
      "startedAt": 1753700000000,
      "completedAt": 1753700005000,
      "durationMs": 5000,
      "children": [
        {
          "nodeId": "check_cache",
          "label": "数据准备",
          "status": "completed",
          "startedAt": 1753700000000,
          "completedAt": 1753700001000,
          "durationMs": 1000,
          "output": {"summary": "..."}
        }
      ]
    }
  ],
  "currentNodeId": "trader",
  "progress": 0.65,
  "updatedAt": 1753700010000
}
```

- 时间戳为 **epoch 毫秒**（前端 `Date.now()` 同源）。
- `currentNodeId` 为运行中节点 id，无运行节点时为 `""`。
- `progress` = completed 节点数 / 总节点数（0~1）。
- 后端在**每个 node_complete** 后写一次快照；node_timing 到达时（如有）也更新一次。node_start 时也写一次（让切回端能看到 running 节点的 startedAt）。
- 快照序列化结构 = 前端 `LayerNode[]` 的 JSON 直出（字段名一致），前后端共用一份事实源。后端维护快照时按 `pipelineTree.ts` 的 `applyNodeEvent` 等价语义用 Python 实现（`pipeline_runner.py` 内）。

---

### Task 1: session_store 新增 pipeline_snapshot 列与读写

**Files:**
- Modify: `src/finance_agent/session_store.py`（init_db 迁移列表、新增两个函数）
- Test: `tests/test_session_store.py`（若无则新建，复用 tmp_path sqlite）

**Interfaces:**
- Produces:
  - `update_pipeline_snapshot(session_id: str, snapshot: dict) -> bool` —— 将 dict JSON 序列化写入 `sessions.pipeline_snapshot`；返回是否更新到行。
  - `get_session(session_id)` 返回 dict 自动包含 `pipeline_snapshot` 键（str | None，JSON 文本，未反序列化）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_session_store.py 中新增
import json

from finance_agent import session_store


def test_pipeline_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")

    snapshot = {"layerTree": [], "currentNodeId": "trader", "progress": 0.5, "updatedAt": 123}
    assert session_store.update_pipeline_snapshot(sid, snapshot) is True

    row = session_store.get_session(sid)
    assert row is not None
    assert json.loads(row["pipeline_snapshot"]) == snapshot


def test_pipeline_snapshot_default_none(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "test.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="贵州茅台", status="running")
    row = session_store.get_session(sid)
    assert row["pipeline_snapshot"] is None
```

先确认 `_DB_PATH`（或等效常量）在 `session_store.py` 中的真实名称；若模块用的是函数内局部路径，则改为 monkeypatch 该函数或按其现有测试的做法注入临时库。先看现有 `tests/` 下是否已有 session_store 测试可复用其注入方式。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_session_store.py -v`
Expected: FAIL（`update_pipeline_snapshot` 不存在 / 无 `pipeline_snapshot` 键）

- [ ] **Step 3: 实现**

`session_store.py` 改动：

1. init_db 迁移列表追加一行：

```python
        ("pipeline_snapshot", "ALTER TABLE sessions ADD COLUMN pipeline_snapshot TEXT"),
```

2. 文件末尾新增函数（风格对齐现有 update_* 函数，中文注释）：

```python
def update_pipeline_snapshot(session_id: str, snapshot: dict) -> bool:
    """持久化管线进度快照（JSON）。返回是否更新到行。"""
    conn = _get_db()
    cur = conn.execute(
        "UPDATE sessions SET pipeline_snapshot = ? WHERE session_id = ?",
        (json.dumps(snapshot, ensure_ascii=False), session_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0
```

确认文件顶部已 `import json`（已有 `_safe_dump` 用到则应已导入）。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_session_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/session_store.py tests/test_session_store.py
git commit -m "feat: session_store 新增 pipeline_snapshot 列与读写"
```

---

### Task 2: PipelineRunner 后台执行器（后台线程跑 graph.stream + 事件队列 + 快照）

**Files:**
- Create: `src/finance_agent/pipeline_runner.py`
- Test: `tests/test_pipeline_runner.py`

**Interfaces:**
- Consumes: Task 1 的 `update_pipeline_snapshot` / `update_session_status`；`api._run_graph_streaming`（本任务中被重构复用，见下）。
- Produces:
  - `PipelineRunner.start(session_id: str, event_source: Callable[[], Generator[str, None, None]], initial_snapshot: dict) -> None` —— 幂等；已在跑则直接返回。
  - `PipelineRunner.is_running(session_id: str) -> bool`
  - `PipelineRunner.get_events(session_id: str) -> list[str]` —— 取走（消费）当前累计的 SSE 事件字符串（供 SSE 订阅端轮询拉取）。
  - `PipelineRunner.mark_swept_failed(statuses: Iterable[str] = ("running",)) -> int` —— 启动清扫：把悬挂 running 会话置 failed，返回处理条数。

设计要点（写给实现者的决策依据）：
- `graph.stream` 是同步生成器，后台执行用 `threading.Thread`（不是 asyncio.Task——同步迭代器在 asyncio task 里会阻塞事件循环；`_stream_from_sync` 现有做法也是 threadpool，线程模型一致）。
- `_running: dict[str, _RunState]`；`_RunState` 内含 `thread: Thread`、`events: list[str]`（SSE 字符串累积）、`lock: threading.Lock`、`done: bool`。
- 后台线程体：迭代 `event_source()`，每拿到一条 SSE 字符串：append 到 `events`；解析其 `data:` JSON，若为 `node_start/node_complete/node_timing` 则用 `apply_node_event` 的 Python 等价实现更新内存快照并 `update_pipeline_snapshot`；若为 `report_ready/error` 则收尾（写最终快照、置 `done=True`）。迭代结束后置 `done=True` 并从 `_running` 移除（保留事件缓冲到首次被取走后清理，或 TTL 清理——MVP：done 后保留事件直到被 `get_events` 取空后移除条目）。
- 快照维护：Python 侧 `apply_node_event` 等价实现，直接照搬 `pipelineTree.ts` 的语义（状态单调、layer 状态推导、时间戳优先级 server_* > nowMs），节点→layer 映射表与前端 `LAYER_TREE_CONFIG` 对齐。该映射从 `api.py` 现有的 `_NODE_MAP`（含 layer 字段）派生，不重复硬编码节点清单：构建 `{node_id: layer_id}`，layer 顺序用 `_ALL_NODES` 推导。
- **改造 `_run_graph_streaming`**：抽出纯事件生成逻辑不动，仅让调用方可选。本任务不改它；Task 3 接线时由 api.py 传入一个闭包 `lambda: _run_graph_streaming(...)`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_pipeline_runner.py
import json
import time

from finance_agent import session_store
from finance_agent.pipeline_runner import PipelineRunner


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _fake_events():
    """模拟 _run_graph_streaming 的 SSE 事件序列（两节点 + 完成）。"""
    yield _sse({"type": "analysis_start", "session_id": "s1"})
    yield _sse({"type": "node_start", "node_id": "check_cache", "layer": "PREP"})
    yield _sse({"type": "node_complete", "node_id": "check_cache", "layer": "PREP",
                "completed": ["check_cache"], "progress": 0.03, "output": {"summary": "ok"}})
    yield _sse({"type": "node_start", "node_id": "fetch_data", "layer": "PREP"})
    yield _sse({"type": "node_complete", "node_id": "fetch_data", "layer": "PREP",
                "completed": ["check_cache", "fetch_data"], "progress": 0.06, "output": {}})
    yield _sse({"type": "report_ready", "session_id": "s1", "report_markdown": "# 报告"})


def test_start_idempotent_and_events_accumulate(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    PipelineRunner.start(sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0})
    PipelineRunner.start(sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0})  # 幂等不重复启动

    # 等后台线程跑完
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)
    assert not PipelineRunner.is_running(sid)

    events = PipelineRunner.get_events(sid)
    assert any('"node_start"' in e for e in events)
    assert any('"report_ready"' in e for e in events)

    # 快照已持久化
    row = session_store.get_session(sid)
    snap = json.loads(row["pipeline_snapshot"])
    assert snap["currentNodeId"] in ("", "fetch_data")
    assert snap["progress"] > 0


def test_snapshot_tracks_node_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")

    PipelineRunner.start(sid, _fake_events, {"layerTree": [], "currentNodeId": "", "progress": 0.0, "updatedAt": 0})
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    snap = json.loads(session_store.get_session(sid)["pipeline_snapshot"])
    # layerTree 中 check_cache 与 fetch_data 均 completed
    all_children = [c for layer in snap["layerTree"] for c in layer["children"]]
    by_id = {c["nodeId"]: c for c in all_children}
    assert by_id["check_cache"]["status"] == "completed"
    assert by_id["fetch_data"]["status"] == "completed"


def test_sweep_marks_running_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
    n = PipelineRunner.mark_swept_failed()
    assert n >= 1
    assert session_store.get_session(sid)["status"] == "failed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: FAIL（`finance_agent.pipeline_runner` 不存在）

- [ ] **Step 3: 实现 `pipeline_runner.py`**

结构（中文注释，完整实现）：

```python
"""会话级管线后台执行器。

graph.stream 是同步生成器，用独立线程执行，与 SSE 订阅解耦：
客户端断开仅停止订阅，后台线程继续推进管线。
进度快照（layerTree JSON）在每节点事件时持久化到 sessions.pipeline_snapshot，
SSE 端通过 get_events 轮询拉取累积事件。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Generator

from finance_agent import session_store

logger = logging.getLogger(__name__)

_SSE_DATA_RE = re.compile(r"^data: (.*)$", re.MULTILINE)

# 与前端 pipelineTree.LAYER_TREE_CONFIG 对齐的 节点 -> layer 映射。
# 由 api._NODE_MAP 惰性派生（避免模块级循环导入）。
_NODE_TO_LAYER: dict[str, str] | None = None
_LAYER_ORDER: list[str] | None = None


def _node_layer_map() -> tuple[dict[str, str], list[str]]:
    global _NODE_TO_LAYER, _LAYER_ORDER
    if _NODE_TO_LAYER is None:
        from finance_agent.api import _ALL_NODES, _NODE_MAP

        _NODE_TO_LAYER = {nid: info["layer"] for nid, info in _NODE_MAP.items()}
        # layer 顺序按节点出现顺序去重
        order: list[str] = []
        for nid in _ALL_NODES:
            layer = _NODE_TO_LAYER.get(nid)
            if layer and layer not in order:
                order.append(layer)
        _LAYER_ORDER = order
    return _NODE_TO_LAYER, _LAYER_ORDER  # type: ignore[return-value]


# ── layerTree 快照维护（与前端 pipelineTree.applyNodeEvent 语义等价）──


def build_layer_tree() -> list[dict]:
    """构建初始 layerTree（与前端 buildLayerTree 等价）。"""
    node_to_layer, layer_order = _node_layer_map()
    layers: dict[str, list[str]] = {layer: [] for layer in layer_order}
    from finance_agent.api import _ALL_NODES, _NODE_MAP

    for nid in _ALL_NODES:
        info = _NODE_MAP.get(nid)
        if info:
            layers[info["layer"]].append(nid)
    return [
        {
            "id": layer,
            "label": layer,
            "status": "pending",
            "children": [
                {"nodeId": nid, "label": nid, "status": "pending"} for nid in layers[layer]
            ],
        }
        for layer in layer_order
    ]


def apply_node_event(tree: list[dict], event: dict, now_ms: int) -> list[dict]:
    """应用 node_start/node_complete/node_timing 事件（与前端语义等价，不可变更新）。"""
    node_to_layer, _ = _node_layer_map()
    layer_id = node_to_layer.get(event.get("node_id", ""))
    if not layer_id:
        return tree

    new_tree = []
    for layer in tree:
        if layer["id"] != layer_id:
            new_tree.append(layer)
            continue
        children = []
        for child in layer["children"]:
            if child["nodeId"] != event["node_id"]:
                children.append(child)
                continue
            etype = event["type"]
            if etype == "node_timing":
                started = event.get("server_start_ts", child.get("startedAt"))
                duration = event.get("server_duration_ms")
                if duration is None and event.get("server_end_ts") is not None and started is not None:
                    duration = max(0, event["server_end_ts"] - started)
                else:
                    duration = duration if duration is not None else child.get("durationMs")
                children.append({
                    **child,
                    "startedAt": started,
                    "completedAt": event.get("server_end_ts", child.get("completedAt")),
                    "durationMs": duration,
                })
                continue
            if child.get("status") == "completed":
                children.append(child)
                continue
            if etype == "node_start":
                started = event.get("server_start_ts", child.get("startedAt", now_ms))
                children.append({**child, "status": "running", "startedAt": started})
            else:  # node_complete
                started = event.get("server_start_ts", child.get("startedAt", now_ms))
                children.append({
                    **child,
                    "status": "completed",
                    "startedAt": started,
                    "completedAt": now_ms,
                    "durationMs": max(0, now_ms - started),
                    "output": event.get("output", child.get("output")),
                })
        any_running = any(c["status"] == "running" for c in children)
        all_completed = len(children) > 0 and all(c["status"] == "completed" for c in children)
        status = layer["status"]
        if status != "completed":
            if all_completed:
                status = "completed"
            elif any_running:
                status = "running"
        layer_started = layer.get("startedAt")
        if layer_started is None and (any_running or all_completed):
            layer_started = now_ms
        layer_completed = layer.get("completedAt")
        if status == "completed" and layer_completed is None:
            layer_completed = now_ms
        duration = layer.get("durationMs")
        if status == "completed" and layer_started is not None and layer_completed is not None:
            duration = max(0, layer_completed - layer_started)
        new_tree.append({
            **layer,
            "status": status,
            "children": children,
            "startedAt": layer_started,
            "completedAt": layer_completed,
            "durationMs": duration,
        })
    return new_tree


def _current_node(tree: list[dict]) -> str:
    for layer in tree:
        for child in layer["children"]:
            if child["status"] == "running":
                return child["nodeId"]
    return ""


def _progress(tree: list[dict]) -> float:
    total = sum(len(layer["children"]) for layer in tree)
    if total == 0:
        return 0.0
    done = sum(1 for layer in tree for c in layer["children"] if c["status"] == "completed")
    return done / total


# ── 后台执行器 ──


class _RunState:
    def __init__(self, thread: threading.Thread):
        self.thread = thread
        self.events: list[str] = []
        self.lock = threading.Lock()
        self.done = False


class PipelineRunner:
    """管线后台执行：事件累积 + 快照持久化。幂等 start。"""

    _running: dict[str, _RunState] = {}
    _guard = threading.Lock()

    @classmethod
    def is_running(cls, session_id: str) -> bool:
        with cls._guard:
            state = cls._running.get(session_id)
            return state is not None and not state.done

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

    @classmethod
    def get_events(cls, session_id: str) -> list[str]:
        """取走累积的 SSE 事件（消费式）。done 且取空后清理条目。"""
        with cls._guard:
            state = cls._running.get(session_id)
            if state is None:
                return []
            with state.lock:
                events, state.events = state.events, []
            if state.done and not state.events:
                cls._running.pop(session_id, None)
            return events

    @classmethod
    def _run(
        cls,
        session_id: str,
        event_source: Callable[[], Generator[str, None, None]],
        snapshot: dict,
    ) -> None:
        state = cls._running.get(session_id)
        tree = snapshot.get("layerTree") or build_layer_tree()
        try:
            for sse_str in event_source():
                if state is not None:
                    with state.lock:
                        state.events.append(sse_str)
                event = cls._parse_event(sse_str)
                if event is None:
                    continue
                if event.get("type") in ("node_start", "node_complete", "node_timing"):
                    now_ms = int(time.time() * 1000)
                    tree = apply_node_event(tree, event, now_ms)
                    snapshot = {
                        "layerTree": tree,
                        "currentNodeId": _current_node(tree),
                        "progress": _progress(tree),
                        "updatedAt": now_ms,
                    }
                    session_store.update_pipeline_snapshot(session_id, snapshot)
        except Exception:
            logger.exception("后台管线执行异常 session=%s", session_id)
            session_store.update_session_status(session_id, "failed")
        finally:
            if state is not None:
                state.done = True

    @staticmethod
    def _parse_event(sse_str: str) -> dict | None:
        match = _SSE_DATA_RE.search(sse_str)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    @classmethod
    def mark_swept_failed(cls, statuses: tuple[str, ...] = ("running",)) -> int:
        """启动清扫：悬挂 running 会话置 failed（后端重启后 _running 已丢失）。"""
        conn = session_store._get_db()  # noqa: SLF001 - 同模块内部复用连接工厂
        cur = conn.execute(
            f"UPDATE sessions SET status = 'failed' WHERE status IN ({','.join('?' * len(statuses))})",  # noqa: S608
            tuple(statuses),
        )
        conn.commit()
        conn.close()
        return cur.rowcount
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_pipeline_runner.py -v`
Expected: PASS（若 `_NODE_MAP`/`_ALL_NODES` 名称不符，按 api.py 实际顶层常量名调整）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/pipeline_runner.py tests/test_pipeline_runner.py
git commit -m "feat: PipelineRunner 后台执行器（线程跑 graph.stream + 事件队列 + 快照持久化）"
```

---

### Task 3: api.py 接线——管线启动走 PipelineRunner + SSE 订阅事件队列 + 启动清扫

**Files:**
- Modify: `src/finance_agent/api.py`（fast path `api.py:918-939` 与 ReAct 工具触发的管线路径）
- Test: `tests/test_api_pipeline_resume.py`（TestClient 集成测试）

**Interfaces:**
- Consumes: Task 2 的 `PipelineRunner.start/is_running/get_events/mark_swept_failed`、`build_layer_tree`。
- Produces: SSE 端行为契约——SSE 在线时事件照旧逐条推送（来自后台线程的事件队列）；断开不中断后台管线。`GET /api/sessions/{id}` 响应包含 `pipeline_snapshot`（get_session SELECT * 自动带，无需改 endpoint，但需确认序列化）。

设计要点：
- 改造目标：`/api/analyze` 的 fast path（`api.py:920-939`）。当前 `async for event in _stream_from_sync(_run_graph_streaming(...))` 直接驱动图。改为：
  1. `PipelineRunner.start(session_id, lambda: _run_graph_streaming(...), {"layerTree": build_layer_tree(), ...})`
  2. SSE 循环：反复 `PipelineRunner.get_events(session_id)`，yield 事件；无事件时 `await asyncio.sleep(0.2)`；当 `not is_running` 且队列已取空 → 跳出，发 `done`。
- ReAct 工具路径（`stream_agent_to_sse` 内部调 `run_deep_analysis` 工具）若也内嵌 `_run_graph_streaming`：同样改造——先查 `agent_factory.py` 中该工具的实现。若工具内部直接迭代 `_run_graph_streaming` 并 yield 到 agent 流，则把"管线部分"替换为 PipelineRunner + 队列转发。若改造面过大，MVP 允许：ReAct 路径保持现状（断开即中断），仅 fast path 后台化——**实现前必须确认并记录该取舍**（在 commit message 或 tasks.md 批注）。建议优先确认 fast path 是不是前端深度分析的实际入口（前端 `runAnalysis` POST `/api/analyze` 带 `stock_code` 时走 fast path）。
- 启动清扫：FastAPI startup 事件（或 `init_db` 后）调用 `PipelineRunner.mark_swept_failed()`。找 api.py 现有的 `@app.on_event("startup")` 或 lifespan，挂进去。
- `GET /api/sessions/{id}`（`api.py:532`）直接返回 `get_session` dict，`pipeline_snapshot` 为 JSON 字符串——前端解析。确认 endpoint 返回体没有字段白名单过滤；若有则补字段。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_api_pipeline_resume.py
import json
import time

from fastapi.testclient import TestClient

from finance_agent import session_store
from finance_agent.api import app
from finance_agent.pipeline_runner import PipelineRunner


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def test_session_detail_includes_pipeline_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()
    sid = session_store.create_session(stock_code="600519", stock_name="茅台", status="running")
    session_store.update_pipeline_snapshot(sid, {"layerTree": [], "currentNodeId": "x", "progress": 0.1, "updatedAt": 1})

    client = TestClient(app)
    resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_snapshot" in data
    assert json.loads(data["pipeline_snapshot"])["currentNodeId"] == "x"


def test_pipeline_continues_after_sse_disconnect(tmp_path, monkeypatch):
    """核心红线：SSE 断开后后台管线继续推进快照。"""
    monkeypatch.setattr(session_store, "_DB_PATH", tmp_path / "t.db")
    session_store.init_db()

    # 用受控的假事件源替换真实管线（单测级 stub，验证接线而非管线本身）
    import finance_agent.api as api_mod

    def fake_stream(*args, **kwargs):
        yield _sse({"type": "analysis_start", "session_id": "x"})
        for nid in ["check_cache", "fetch_data", "validate_financials"]:
            yield _sse({"type": "node_start", "node_id": nid, "layer": "PREP"})
            time.sleep(0.05)
            yield _sse({"type": "node_complete", "node_id": nid, "layer": "PREP", "output": {}})
        yield _sse({"type": "report_ready", "report_markdown": "# ok"})

    monkeypatch.setattr(api_mod, "_run_graph_streaming", fake_stream)

    client = TestClient(app)
    # 发起分析，读到第一个事件即断开
    with client.stream("POST", "/api/analyze", json={
        "query": "分析贵州茅台", "stock_code": "600519", "stock_name": "贵州茅台",
    }) as resp:
        sid = None
        for line in resp.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("session_id"):
                    sid = ev["session_id"]
                    break
        # 出 with 块即断开连接
    assert sid is not None

    # 等后台推进
    deadline = time.time() + 5
    while PipelineRunner.is_running(sid) and time.time() < deadline:
        time.sleep(0.05)

    snap_raw = session_store.get_session(sid)["pipeline_snapshot"]
    assert snap_raw is not None
    snap = json.loads(snap_raw)
    done_nodes = [c["nodeId"] for layer in snap["layerTree"] for c in layer["children"] if c["status"] == "completed"]
    assert "validate_financials" in done_nodes  # 断开后仍推进到后续节点
```

注意：此测试依赖 api.py 的 `/api/analyze` fast path 实际被改造走 PipelineRunner；改造前该测试应失败（断开后快照不存在或不推进）。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_api_pipeline_resume.py -v`
Expected: FAIL（`pipeline_snapshot` 字段缺失 / 断开后无快照推进）

- [ ] **Step 3: 实现接线**

1. `api.py` 顶部 import：`from finance_agent.pipeline_runner import PipelineRunner, build_layer_tree`
2. fast path（约 `api.py:920-939`）替换为：

```python
        if stock_code and not session_id:
            update_session_for_clarify(
                session_id, stock_code=stock_code, stock_name=stock_name, status="running"
            )
            # 管线后台执行：SSE 仅订阅事件队列，客户端断开不中断管线
            PipelineRunner.start(
                session_id,
                lambda: _run_graph_streaming(
                    stock_code, stock_name, req, analysis_id, start_time, session_id=session_id
                ),
                {"layerTree": build_layer_tree(), "currentNodeId": "", "progress": 0.0,
                 "updatedAt": int(time.time() * 1000)},
            )
            # 订阅事件队列：在线时实时转发，断开仅停止订阅
            while True:
                events = PipelineRunner.get_events(session_id)
                for event in events:
                    yield event
                if not events and not PipelineRunner.is_running(session_id):
                    break
                await asyncio.sleep(0.2)
            yield _sse({...done 事件同现状...})
            return
```

确认 `asyncio` 已导入。done 事件保持现有结构与字段。

3. ReAct 工具路径：先读 `agent_factory.py` 中 `run_deep_analysis` 工具实现，若其内部迭代 `_run_graph_streaming`，则同样改造为 PipelineRunner + 队列转发；若该工具在 agent 流内同步消费且改造牵连大，记录取舍（MVP 仅 fast path 后台化），并在 tasks.md 批注。
4. 启动清扫：找到 app 启动钩子（`@app.on_event("startup")` 或 lifespan），加：

```python
PipelineRunner.mark_swept_failed()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_api_pipeline_resume.py -v`
Expected: PASS

- [ ] **Step 5: 回归后端全套**

Run: `uv run pytest -x -q`
Expected: 全绿（既有 SSE 行为不回归）

- [ ] **Step 6: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_pipeline_resume.py
git commit -m "feat: /api/analyze 管线后台化，SSE 订阅事件队列，启动清扫悬挂 running 会话"
```

---

### Task 4: 前端 pipelineTree 序列化/反序列化

**Files:**
- Modify: `frontend/src/pipelineTree.ts`
- Test: `frontend/src/__tests__/pipelineTree.test.ts`（按现有测试目录约定找位置；若无该文件，看现有 `*.test.ts` 放哪）

**Interfaces:**
- Produces:
  - `serializeLayerTree(tree: LayerNode[]): string` —— JSON 字符串（后端快照的 layerTree 字段）。
  - `deserializeLayerTree(json: string | null | undefined): LayerNode[]` —— 解析快照 layerTree；入参为空/非法时返回 `buildLayerTree()`。

- [ ] **Step 1: 写失败测试**

```typescript
// 追加到现有 pipelineTree 测试文件
import { buildLayerTree, applyNodeEvent, serializeLayerTree, deserializeLayerTree } from '../pipelineTree'

describe('serialize/deserializeLayerTree', () => {
  it('往返一致', () => {
    let tree = buildLayerTree()
    tree = applyNodeEvent(tree, { type: 'node_start', node_id: 'check_cache' }, 1000)
    tree = applyNodeEvent(tree, { type: 'node_complete', node_id: 'check_cache', output: { summary: 'ok' } }, 2000)
    const restored = deserializeLayerTree(serializeLayerTree(tree))
    expect(restored).toEqual(tree)
  })

  it('空输入回退初始树', () => {
    expect(deserializeLayerTree(null)).toEqual(buildLayerTree())
    expect(deserializeLayerTree('not json')).toEqual(buildLayerTree())
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- pipelineTree`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现**

`pipelineTree.ts` 末尾追加（中文注释）：

```typescript
// ── 序列化（会话快照持久化/恢复，resume-pipeline-across-sessions）──

// LayerNode 为纯数据，可直接 JSON；反序列化失败时回退初始树
export function serializeLayerTree(tree: LayerNode[]): string {
  return JSON.stringify(tree)
}

export function deserializeLayerTree(json: string | null | undefined): LayerNode[] {
  if (!json) return buildLayerTree()
  try {
    const data = JSON.parse(json)
    if (!Array.isArray(data)) return buildLayerTree()
    return data as LayerNode[]
  } catch {
    return buildLayerTree()
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test -- pipelineTree`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pipelineTree.ts frontend/src/__tests__/pipelineTree.test.ts
git commit -m "feat: layerTree 序列化/反序列化（会话快照恢复）"
```

---

### Task 5: 前端 selectSession 按 status 恢复 + 条件化 abort + 轮询

**Files:**
- Modify: `frontend/src/types.ts`（SessionDetail 加字段、PipelineSnapshot 类型）
- Modify: `frontend/src/App.tsx`（selectSession 重写恢复逻辑、轮询 hook）
- Test: `frontend/src/__tests__/selectSession.test.tsx`（或按现有 App 测试约定）

**Interfaces:**
- Consumes: Task 4 的 `deserializeLayerTree`；后端 `GET /api/sessions/{id}` 返回的 `pipeline_snapshot`（JSON 字符串）。
- Produces:
  - `interface PipelineSnapshot { layerTree: string; currentNodeId: string; progress: number; updatedAt: number }`（types.ts 导出；`layerTree` 为序列化 JSON 字符串）
  - `SessionDetail` 新增 `pipeline_snapshot: string | null`

恢复逻辑（对齐 design.md §3）：
- `selectSession` 开头不再无条件 `abortStreaming()`：仅当**离开**的会话是纯流式（无 pipelineMsgRef 或当前流为快速模式）时 abort；深度管线会话 abort 仅断开订阅（后端已后台化，前端 abort 本来就是断订阅——保留 abort 但语义不变，因为后端不再受影响）。**简化决策**：保留 `abortStreaming()` 调用（前端断开 SSE 即可，后端管线由 PipelineRunner 保护不受影响），无需条件化——但 tasks.md 要求条件化，实现时以「快速模式流仍 abort、深度管线也 abort（仅断订阅）」语义为准，注释说明。
- `data.status === 'running' && data.pipeline_snapshot` → 构建 pipelineMsg（`layerTree: deserializeLayerTree(snapshot.layerTree)`、`currentNode: snapshot.currentNodeId`、`progress`），`pipelineMsgRef.current = pm`，messages 追加，`setAppState('analyzing')`，启动轮询。
- `data.status === 'completed' && data.pipeline_snapshot` → reportMsg（现有逻辑）+ pipelineMsg（静态完成树）插入 messages（管线消息在报告消息之前），`setAppState('report')`。
- 轮询：`useEffect` + `setInterval(2000)`，依赖 `currentSessionId` 与 appState==='analyzing'；轮询 `GET /api/sessions/{id}`，解析快照更新 `pipelineMsgRef` 与 messages；`status !== 'running'` 时停止（completed → 恢复报告并 `setAppState('report')`）。
- 轮询期间运行中节点耗时由现有 `nowMs` 渲染机制实时递增（`PipelineTimeline` 已接收 `nowMs` prop），无需额外处理。

- [ ] **Step 1: 写失败测试**

按前端现有测试风格（查 `frontend/src/__tests__/` 现有 App 级测试是否用 vitest + testing-library + fetch stub）。测试用例：

```typescript
// 伪代码骨架，按现有测试基建落地
it('running 会话恢复时间轴并进入 analyzing', async () => {
  const snapshot = JSON.stringify({
    layerTree: JSON.stringify(treeWithRunningNode), // 含一个 running 子节点
    currentNodeId: 'trader', progress: 0.5, updatedAt: Date.now(),
  })
  mockFetchSession({ status: 'running', pipeline_snapshot: snapshot, chat_history: [], ... })
  await selectSession('s1')
  expect(screen.getByTestId('pipeline-timeline')).toBeInTheDocument() // 按实际渲染断言
  // appState analyzing → 轮询启动
})

it('completed 会话恢复报告+静态时间轴', ...)
it('无快照会话走现有逻辑（report/chat）', ...)
```

先勘察 `frontend/src/__tests__/` 现有 App/selectSession 测试的 mock 方式，复用其基建写真实测试代码。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- selectSession`
Expected: FAIL（恢复逻辑不存在）

- [ ] **Step 3: 实现**

1. `types.ts`：

```typescript
// 管线进度快照（后端 sessions.pipeline_snapshot，JSON 字符串内嵌 layerTree）
export interface PipelineSnapshot {
  layerTree: string
  currentNodeId: string
  progress: number
  updatedAt: number
}

export interface SessionDetail extends SessionMeta {
  // ...现有字段...
  pipeline_snapshot: string | null
}
```

2. `App.tsx` `selectSession`：在现有逻辑基础上插入分支（保留 report/chat_history 恢复）：

```typescript
      // 管线快照恢复（resume-pipeline-across-sessions）
      const snapshot: PipelineSnapshot | null = data.pipeline_snapshot
        ? JSON.parse(data.pipeline_snapshot)
        : null

      if (data.status === 'running' && snapshot) {
        // 运行中：恢复分层时间轴 + 轮询进度
        const pm: UIMessage = {
          id: genId(),
          type: 'pipeline',
          content: '',
          completedNodes: [],
          currentNode: snapshot.currentNodeId,
          nodeOutputs: {},
          progress: snapshot.progress,
          startedAt: Date.now(),
          layerTree: deserializeLayerTree(snapshot.layerTree),
        }
        pipelineMsgRef.current = pm
        setMessages([...newMessages, pm])
        setAppState('analyzing')
        return
      }
      if (data.status === 'completed' && snapshot) {
        // 已完成：静态时间轴插在报告消息之前
        const pm: UIMessage = {
          id: genId(),
          type: 'pipeline',
          content: '',
          completedNodes: [],
          currentNode: '',
          nodeOutputs: {},
          progress: 1,
          layerTree: deserializeLayerTree(snapshot.layerTree),
        }
        // 插到 reportMsg 前（reportInserted 逻辑内处理）
      }
      // 其余走现有逻辑
```

completed 分支与现有 reportMsg 插入顺序整合：pipelineMsg 紧跟在触发分析的 user 消息后、reportMsg 前。

3. 轮询 hook：

```typescript
  // 运行中会话轮询快照（2s，完成即停）
  useEffect(() => {
    if (appState !== 'analyzing' || !currentSessionId) return
    // 仅恢复态（无活跃 SSE）时轮询：有 abortRef 说明 SSE 在线，无需轮询
    if (abortRef.current) return
    const timer = setInterval(async () => {
      try {
        const resp = await fetch(`/api/sessions/${currentSessionId}`)
        if (!resp.ok) return
        const data: SessionDetail = await resp.json()
        if (data.status === 'running' && data.pipeline_snapshot) {
          const snap: PipelineSnapshot = JSON.parse(data.pipeline_snapshot)
          const pm = pipelineMsgRef.current
          if (pm) {
            const updated: UIMessage = {
              ...pm,
              layerTree: deserializeLayerTree(snap.layerTree),
              currentNode: snap.currentNodeId,
              progress: snap.progress,
            }
            pipelineMsgRef.current = updated
            updateMessage(pm.id, updated)
          }
        } else if (data.status === 'completed') {
          // 后台完成：恢复报告 + 最终静态时间轴
          selectSession(currentSessionId)
        }
      } catch { /* 轮询失败静默重试 */ }
    }, 2000)
    return () => clearInterval(timer)
  }, [appState, currentSessionId])
```

`updateMessage` 复用 App.tsx 现有函数（`App.tsx:676` 附近）。

- [ ] **Step 4: 运行测试确认通过 + tsc**

Run: `cd frontend && npm test -- selectSession ; npx tsc --noEmit`
Expected: PASS / 无类型错误

- [ ] **Step 5: 前端全套回归**

Run: `cd frontend && npm test`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types.ts frontend/src/App.tsx frontend/src/__tests__/
git commit -m "feat: selectSession 按会话状态恢复管线（running 轮询 / completed 静态时间轴）"
```

---

### Task 6: E2E + 验证

**Files:**
- Test: `tests/e2e/` 下新增 spec（按现有 E2E 基建，Playwright）
- Modify: `openspec/changes/resume-pipeline-across-sessions/tasks.md`（勾选）
- Create: `tests/validation/resume-pipeline-across-sessions-validation.md`

- [ ] **Step 1: E2E 用例（stub 管线，真实前后端）**

用例 1：发起深度分析（`TESTING=1` stub LLM）→ 管线运行中点击侧边栏切换到另一会话 → 等待 3s → 切回 → 断言分层时间轴可见、进度较切换前推进（快照 updatedAt 或 completed 节点数增加）。
用例 2：管线完成后切回该会话 → 断言报告可见 + 静态时间轴各节点 completed。
用例 3：既有 E2E 套件不回归。

遵守红线：不 mock 业务接口；LLM 用 `TESTING=1` stub；通过前端 UI 真实操作（点击会话列表项）。

- [ ] **Step 2: 运行 E2E**

Run: 按项目 E2E 运行方式（查 `tests/e2e/` README 或 package.json scripts）
Expected: 新用例 PASS + 旧套件不回归

- [ ] **Step 3: 全量验证门禁**

Run: `uv run pytest -q`；`uv run ruff check`；`cd frontend && npm test ; npx tsc --noEmit`
Expected: 全绿

- [ ] **Step 4: 人工验证报告**

真实 LLM 下手动验证并落 `tests/validation/resume-pipeline-across-sessions-validation.md`：
- 发起真实分析 → 切换会话 → 观察后端日志/Langfuse 确认管线继续 → 切回确认时间轴恢复且进度推进 → 完成后切回确认报告+静态时间轴。
- 记录：操作步骤、截图/日志摘录、结论。

- [ ] **Step 5: 勾选 tasks.md + Commit**

```bash
git add tests/e2e/ tests/validation/ openspec/changes/resume-pipeline-across-sessions/tasks.md
git commit -m "test: 切换会话恢复管线 E2E 与人工验证报告"
```

---

## Self-Review 记录

- **Spec 覆盖**：proposal 三条恢复分支（running/completed/failed）→ Task 5（running/completed）；failed 分支 = 现有逻辑已显示失败/无快照回退，设计文档未要求新 UI，Task 5 Step 3 的 else 分支覆盖。D1 后台化 → Task 2/3；D2 轮询 → Task 5；D3 快照 → Task 1/2；D5 清扫 → Task 3；D6 幂等 → Task 2。tasks.md 0.1 技术前提验证已在「现状关键事实」以代码勘察闭环（同步生成器 + SSE 取消 ⇒ 必须后台化），实施时由 Task 3 的断线续跑测试实证。
- **Placeholder 扫描**：Task 5 的 completed 分支插入顺序留有实现弹性（依赖现有 reportMsg 插入逻辑的细节），实现者需读 App.tsx:150-175 整合；E2E Step 1 未给完整代码（依赖现有 E2E 基建勘察），实现者先读 `tests/e2e/` 现有 spec 风格。
- **类型一致性**：快照契约（顶部 JSON）与 Task 1 测试、Task 2 `_run` 快照写入、Task 4 `PipelineSnapshot` 接口、Task 5 解析一致（`layerTree` 为内嵌 JSON 字符串，`currentNodeId/progress/updatedAt` 平铺）。
