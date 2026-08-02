# 可恢复流式生成架构完善设计

| 项 | 值 |
| --- | --- |
| 文档状态 | 设计定稿，待实施 |
| 对应文档 | `docs/resume-stream-on-session-switch-设计档案.md` |
| 影响范围 | 后端 `stream_registry.py` / `api.py` / `session_store.py` / `pipeline_runner.py`；前端 `App.tsx` / `types.ts` |
| 目标 | 消除实现与设计档案之间的 10 个偏离点，使架构完全一致 |

---

## 1. 偏离点清单与修复方案

### 1.1 后端协议层修复

#### #1 SSE 帧带 `id: {seq}`

**当前**：`_sse()` 只输出 `data: {...}\n\n`，seq 注入到 JSON 内部。

**修复**：在 `data:` 行前添加 `id:` 行：

```python
def _sse(data: dict) -> str:
    seq = data.get("seq")
    id_line = f"id: {seq}\n" if seq is not None else ""
    return f"{id_line}data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
```

使原生 EventSource 的自动 `Last-Event-ID` 机制生效。

#### #3 终态竞态 CAS

**当前**：cancel 与自然完成可能产生两条终态事件，无 CAS 检查。

**修复**：在 `stream_registry.publish` 中做终态事件条件插入：

```python
async def publish(self, session_id, event):
    eventType = event.get("type")
    if eventType in ("done", "interrupted", "error"):
        existing = await asyncio.to_thread(
            session_store.has_terminal_event, session_id
        )
        if existing:
            return 0  # 已有终态，放弃
    seq = await asyncio.to_thread(session_store.append_session_event, ...)
    ...
```

需在 `session_store` 中新增 `has_terminal_event(session_id) -> bool` 查询：检查 journal 中是否已存在 `done`/`interrupted`/`error` 类型事件。

#### #4 cancel 幂等

**当前**：无活跃任务时返回 404。

**修复**：无活跃任务时检查是否已有终态事件，有则返回终态：

```python
async def cancel_session(session_id: str):
    result = await stream_registry.cancel(session_id)
    pipeline_result = PipelineRunner.cancel(session_id)  # Part 2 新增
    if not result and not pipeline_result:
        terminal = await asyncio.to_thread(
            session_store.get_terminal_event, session_id
        )
        if terminal:
            return {"ok": True, "status": terminal["type"]}
        raise HTTPException(404, "No active task for this session")
    return {"ok": True, "status": "interrupted"}
```

需在 `session_store` 中新增 `get_terminal_event(session_id) -> dict | None`：返回 journal 中最后一条终态事件。

#### #6 204 语义

**当前**：无活跃任务时下发 `done`/`interrupted` 终态事件后关闭流。

**修复**：无活跃任务且无事件可重放时返回 204：

```python
async def stream_session(...):
    events = await asyncio.to_thread(
        session_store.list_session_events, session_id, after_seq
    )
    has_active = stream_registry.is_active(session_id) or PipelineRunner.is_running(session_id)
    if not events and not has_active:
        return Response(status_code=204)
    # 有事件或活跃任务：正常 SSE 流
    ...
```

#### #10 心跳间隔

**当前**：15 秒。

**修复**：改为 10 秒，与设计文档"5~10 秒"对齐。

---

### 1.2 Fast path 桥接到 stream_registry

#### #2 双轨制统一

**当前**：Fast path 用 PipelineRunner（线程 + 内存 events），不走 stream_registry 的 journal。

**修复方案：桥接统一**

保留 PipelineRunner 的线程执行模型，但在 `_run` 循环中将事件桥接到 `stream_registry.publish`。

**PipelineRunner._run 改造**：

```python
@classmethod
def _run(cls, session_id, event_source, snapshot, loop):
    # loop: 主事件循环引用（由调用方传入）
    ...
    for sse_str in event_source():
        if state.cancel_event.is_set():
            # 中断：publish interrupted 终态
            asyncio.run_coroutine_threadsafe(
                stream_registry.publish(session_id, {"type": "interrupted"}), loop
            ).result(timeout=5)
            break
        # 解析事件 dict
        event = cls._parse_event(sse_str)
        # 桥接到 stream_registry（经 run_coroutine_threadsafe）
        if event:
            asyncio.run_coroutine_threadsafe(
                stream_registry.publish(session_id, event), loop
            ).result(timeout=5)
        # 保留现有 snapshot 持久化逻辑
        ...
    finally:
        state.done = True
        # 向 journal 写入终态事件（CAS 保护，避免重复）
        terminal = {"type": "error"} if failed else {"type": "done"}
        asyncio.run_coroutine_threadsafe(
            stream_registry.publish(session_id, terminal), loop
        ).result(timeout=5)
```

关键点：
- `PipelineRunner.start` 接收主事件循环引用 `asyncio.get_event_loop()`
- `publish` 经 `run_coroutine_threadsafe` 跨线程调用，安全写入 journal + fan-out
- `future.result(timeout=5)` 确保事件落库后才继续

**Fast path 不调 `stream_registry.start`**（不创建 `_run_task` 包装），仅借用 `publish` 的 journal 通道。`subscribe` 从 journal 重放 + 检查 `PipelineRunner.is_running` 判断活跃状态。

> **session_created 事件注意**：当前 Fast path 的 `event_stream` 在开头直接 `yield _sse({"type": "session_created", ...})`，此事件不经过 journal。改造后需将此事件也通过 `stream_registry.publish` 写入 journal，确保恢复端点能重放。

**SSE 端点统一**：Fast path 的 `event_stream` 从轮询改为订阅：

```python
# 改造后
async def sse_forward():
    async for event in stream_registry.subscribe(session_id, after_seq=0):
        yield _sse(event)
```

**subscribe 增加 PipelineRunner 活跃检查**：

> **循环依赖注意**：`stream_registry.py` 需检查 `PipelineRunner.is_running`，而 `pipeline_runner.py` 需调用 `stream_registry.publish`。在 `stream_registry.py` 中使用延迟导入（函数内 `from finance_agent.pipeline_runner import PipelineRunner`）避免循环依赖。

```python
# 2. 检查是否有活跃任务
stream = self._streams.get(session_id)
pipeline_active = PipelineRunner.is_running(session_id)
has_active = (stream and stream.task and not stream.task.done()) or pipeline_active
if not has_active:
    # 无活跃任务：下发终态
    ...
```

**cancel 支持**：PipelineRunner 新增 `threading.Event` 取消标志和 `cancel` 方法：

```python
class _RunState:
    def __init__(self, thread):
        ...
        self.cancel_event = threading.Event()

@classmethod
def cancel(cls, session_id) -> bool:
    state = cls._running.get(session_id)
    if not state or state.done:
        return False
    state.cancel_event.set()
    state.thread.join(timeout=5)
    return True
```

---

### 1.3 后端健壮性修复

#### #5 `_persist_collector` 时机 - 运行中增量持久化

**当前**：`_persist_collector` 只在 agent 完成时调用，运行中会话的 `chat_history` 只有 user 消息。

**修复**：在 SSE 循环中定时增量持久化（每 10 秒）：

```python
lastPersistTime = time.time()
PERSIST_INTERVAL = 10

async for sse_str in stream_agent_to_sse(...):
    data = _parse_sse_data(sse_str)
    if data is not None:
        collector.feed(data)
        await stream_registry.publish(session_id, data)
        if time.time() - lastPersistTime > PERSIST_INTERVAL:
            _upsert_assistant_chat(session_id, collector)
            lastPersistTime = time.time()

_persist_collector(session_id, collector)  # 最终持久化
```

新增 `_upsert_assistant_chat`（upsert 语义）和 `session_store.upsert_chat`（查找最后一条 assistant 消息，存在则更新，无则追加）。

#### #7 seq 去重防线

**当前**：前端只更新 `lastSeq`，不跳过旧事件。

**修复**：三个 SSE 处理循环中统一添加 seq 去重检查：

```typescript
const seq = (event as SSEEvent & { seq?: number }).seq
if (seq !== undefined && seq <= state.lastSeq) {
    continue  // 跳过旧事件
}
if (seq !== undefined && seq > state.lastSeq) {
    state.lastSeq = seq
}
```

#### #8 重放缝合竞态 - 先注册队列再读日志

**当前**：`subscribe` 先读日志再注册队列，虽有"补漏"但非设计文档要求的方式。

**修复**：调整 `subscribe` 步骤顺序为"先注册队列，再读日志"：

1. 检查活跃任务并注册实时队列
2. 读日志重放（注册队列后新事件不会丢失）
3. 无活跃任务时下发终态
4. 补漏（重放期间产生的新事件）
5. 消费实时队列

seq 去重消解重叠段。

---

### 1.4 前端统一化

#### #9 重放/实时/首发走同一处理函数

**当前**：`startAnalysis`、`resumeStream`、`quickChat` 三个独立的 SSE 处理循环，代码重复。

**修复**：提取统一的 `handleSSEEvent(event, sessionId)` 函数，包含：
1. seq 去重检查
2. 会话隔离（非当前视图事件缓冲）
3. `session_created` 幂等
4. 终态事件处理（interrupted/done/error）
5. 管线事件路由（analysis_start/node_start/node_complete/report_chunk/report_ready）
6. 对话流事件路由（thinking_token/chat_token/tool_call/tool_result/search_*）
7. 返回值：true=已处理，false=未处理

三个调用方简化为统一模式：

```typescript
for (const line of lines) {
    if (!line.startsWith('data: ')) continue
    const event: SSEEvent = JSON.parse(line.slice(6))
    handleSSEEvent(event, sessionId)
}
```

---

## 2. 新增函数清单

### 后端

| 文件 | 函数 | 说明 |
| --- | --- | --- |
| `session_store.py` | `has_terminal_event(session_id) -> bool` | 检查 journal 中是否已有终态事件 |
| `session_store.py` | `get_terminal_event(session_id) -> dict \| None` | 返回最后一条终态事件 |
| `session_store.py` | `upsert_chat(session_id, role, content, ...)` | upsert 语义的 chat 持久化 |
| `stream_registry.py` | `publish` 修改 | 增加 CAS 终态检查 |
| `stream_registry.py` | `subscribe` 修改 | 先注册队列再读日志 + PipelineRunner 活跃检查 |
| `pipeline_runner.py` | `_run` 修改 | 桥接 publish + cancel 标志 + 终态 publish |
| `pipeline_runner.py` | `cancel` 新增 | 设置取消标志 + join 线程 |
| `api.py` | `_sse` 修改 | 添加 `id:` 行 |
| `api.py` | `cancel_session` 修改 | 幂等返回 + PipelineRunner.cancel |
| `api.py` | `stream_session` 修改 | 204 语义 + 心跳 10s |
| `api.py` | `_run_react_analysis` / `_run_chat_task` 修改 | 定时增量持久化 |
| `api.py` | `_upsert_assistant_chat` 新增 | 增量持久化 collector 内容 |

### 前端

| 文件 | 函数 | 说明 |
| --- | --- | --- |
| `App.tsx` | `handleSSEEvent` 新增 | 统一 SSE 事件处理器 |
| `App.tsx` | `startAnalysis` / `resumeStream` / `quickChat` 修改 | 调用 `handleSSEEvent` |

---

## 3. 测试计划

| 层 | 用例 |
| --- | --- |
| 单测（后端） | SSE 帧包含 `id:` 行；终态 CAS 拒绝重复；cancel 幂等返回终态；204 语义；upsert_chat 幂等；subscribe 先注册再读日志不丢事件；PipelineRunner 桥接 publish；PipelineRunner.cancel 设置标志 |
| 单测（前端） | seq 去重跳过旧事件；handleSSEEvent 统一处理所有事件类型；per-session 状态隔离 |
| E2E | Fast path 中途切会话切回内容继续增长；ReAct 路径切回内容继续增长；显式停止后中断标记刷新后仍在；双 cancel 幂等；cancel 与完成竞态以日志终态为准 |

---

## 4. 实施顺序

1. **后端协议层**（#1, #3, #4, #6, #10）- 独立改动，风险最低
2. **后端健壮性**（#5, #7, #8）- 依赖协议层
3. **Fast path 桥接**（#2）- 依赖健壮性层的 subscribe 改造
4. **前端统一化**（#9）- 依赖后端所有改动完成

每个阶段完成后运行 Playwright CLI 验证脚本确认行为正确。
