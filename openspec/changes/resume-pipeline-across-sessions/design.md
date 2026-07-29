# Design: resume-pipeline-across-sessions

## 核心架构前提

当前 `run_deep_analysis` 内部的 `graph.stream` 在 SSE 生成器内执行，客户端断开（abort）→ 生成器取消 → LangGraph 中断。因此"切换会话后台继续跑"要求**管线执行与 SSE 订阅解耦**。

## 方案：后台 task 执行管线 + SSE 订阅进度

### 1. 管线执行下沉到后台 task

新增 `PipelineRunner`（`pipeline_runner.py`）：

```python
class PipelineRunner:
    """会话级管线后台执行器：管线在独立 asyncio task 中运行，
    进度快照持久化到 session_store；SSE 仅订阅快照/事件，断开不中断管线。"""

    _running: dict[str, asyncio.Task] = {}  # session_id -> 后台任务

    @classmethod
    def start(cls, session_id, graph, initial_state, config):
        # 已运行则复用（幂等，切回会话不重复启动）
        if session_id in cls._running:
            return
        task = asyncio.create_task(cls._run(session_id, graph, initial_state, config))
        cls._running[session_id] = task

    @classmethod
    async def _run(cls, session_id, graph, initial_state, config):
        # graph.stream 在此后台 task 内执行，不受 SSE 断开影响
        # 每节点完成时：更新 session 管线快照（layerTree JSON）
        # 完成/失败时：写 session report/agent_process，更新 status，清理 _running
```

- 管线事件（node_start/node_complete/node_timing/thinking）写入**会话级事件队列**，SSE 订阅该队列（而非直接驱动 graph）。
- 快照（layerTree 状态）在每节点完成时持久化到 sessions 表新列 `pipeline_snapshot`（JSON）。

### 2. 会话管线快照持久化（session_store）

sessions 表新增列：
- `pipeline_snapshot TEXT`（JSON）：`{"layerTree": [...], "currentNodeId": str, "progress": float, "updatedAt": epoch_ms}`
- 复用现有 `status`（running/completed/failed/clarifying）

新增函数：
- `update_pipeline_snapshot(session_id, snapshot: dict)`
- `get_session` 已 SELECT *，自动包含新列（迁移用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`）

### 3. 前端恢复逻辑（selectSession）

```
GET /api/sessions/{id} 返回 { status, pipeline_snapshot, report_markdown, ... }

selectSession:
  不再无条件 abortStreaming() —— 仅当切换"离开"的会话有进行中的快速模式流时才 abort
  （深度管线改由后端后台续跑，前端无需 abort）

  if session.status === 'running' && pipeline_snapshot:
    # 恢复运行中的管线 UI
    pipelineMsg = { type: 'pipeline', layerTree: deserialize(snapshot.layerTree),
                    currentNode: snapshot.currentNodeId, ... }
    pipelineMsgRef.current = pipelineMsg
    setMessages([...history, pipelineMsg])
    setAppState('analyzing')
    # 重新订阅进度：重连 SSE（带 session_id 续传）或轮询快照
    resumePipelineStream(session_id)
  elif session.status === 'completed' && pipeline_snapshot:
    # 恢复报告 + 已完成静态时间轴
    reportMsg = {...}
    pipelineMsg = { type: 'pipeline', layerTree: snapshot.layerTree（全 completed）, ... }
    setMessages([...history, pipelineMsg, reportMsg])
    setAppState('report')
  else:
    # 现有逻辑（chat / 无快照）
```

### 4. 断线重连：SSE 续传 vs 轮询

| 方案 | 评估 |
|------|------|
| **轮询快照**（选定，MVP） | 切回后每 2s 轮询 `GET /api/sessions/{id}` 的 pipeline_snapshot，更新 layerTree；简单可靠，进度粒度=节点级（足够时间轴展示）。报告完成后 status 变 completed，停止轮询 |
| SSE 续传 | 需会话级事件队列 + Last-Event-ID，实时性好但复杂度高，作为后续增强 |

MVP 用轮询：运行中节点耗时靠前端 `nowMs - startedAt` 实时递增（无需后端推送），节点完成经轮询快照更新。

### 5. layerTree 序列化

`pipelineTree.ts` 新增：
- `serializeLayerTree(tree: LayerNode[]): SerializedLayer[]`
- `deserializeLayerTree(data: SerializedLayer[]): LayerNode[]`

LayerNode 已是纯数据（id/status/startedAt/durationMs/output/summary/expandedOverride 除外），可直接 JSON。

### 6. 中断语义变化

- **旧**：selectSession → abortStreaming 中断一切
- **新**：深度管线不 abort（后台续跑）；快速模式流仍 abort（无管线、无恢复价值）

### 7. 并发与边界

- 同一会话重复 start 幂等（`_running` 检查）
- 后端重启：`_running` 丢失，但 sessions.status 可能停留 running → 需启动时将 running 标记为 failed（或恢复点），MVP 标记 failed + 提示
- 多会话并行管线：`_running` 按 session_id 隔离，天然支持

### 8. ReAct 主链路接入（实施期补充决策，2026-07-29）

**发现**：前端 `startAnalysis` 从不传 `stockCode`（App.tsx:870/884），fast path（`stock_code and not req.session_id`）在真实 UI 下不可达；自然语言深度分析全部走 ReAct 路径（`agent_factory.run_deep_analysis` 工具）。该工具自带 executor 线程 + chunk_queue，不经 PipelineRunner → 快照不写、status 不置 running → 「切换会话恢复」对真实主链路不生效。

**决策（分两层）**：

1. **快照回调（本 change 内）**：`build_agent` 已有 `session_id`（kwargs）。`run_deep_analysis` 工具内复用 `pipeline_runner` 的 `build_layer_tree`/`apply_node_event`，在工具线程内维护快照：节点首现（node_start 语义）、node_complete、node_timing 各写一次 `update_pipeline_snapshot`；工具入口置 `status='running'`，循环结束写 `status='completed'`（报告落库仍在 api.py agent 路径终局由 metadata 驱动，此处仅保证断开时状态不悬挂），异常写 `failed`。**不改事件流**——SSE 仍经 chunk_queue → StreamEvent 实时推送，在线体验不变。
2. **完整后台化（后续 change）**：ReAct Agent 的澄清轮 + LLM 编排与管线在同一工具协程内，无法简单下沉为独立线程。切走断开后 Agent 编排流仍中断；管线本体已在独立线程，完成与否取决于生成器取消语义——**切回恢复的主要场景（运行中恢复时间轴、完成后恢复报告）由快照 + 轮询闭环覆盖**；「断开后管线 100% 续跑到底」的强保证留待后续 change（需引入会话级管线句柄注册表，Agent 流断开后由句柄继续驱动）。

## 数据流

```
用户发起管线
  → api.py 创建 session(running) + PipelineRunner.start(后台 task)
  → 后台 task: graph.stream → 节点事件 → 更新 pipeline_snapshot + 事件队列
  → SSE（在线时）: 订阅事件队列实时推送
用户切换会话 → 前端 abort SSE（仅断开订阅）→ 后台 task 继续
用户切回 → GET session → status=running + snapshot → 恢复时间轴 → 轮询快照
管线完成 → 后台 task 写 report + status=completed → 前端轮询到 → 显示报告
```

## 测试策略

- **后端单测**：PipelineRunner 启动幂等、快照持久化、SSE 断开后 task 继续（mock graph.stream 验证后台推进）、session 恢复返回快照
- **前端单测**：serialize/deserializeLayerTree、selectSession 按 status 恢复（running→时间轴+轮询、completed→报告+静态时间轴）
- **E2E**：stub 管线运行中切换会话再切回 → 时间轴恢复且进度推进；完成后切回 → 报告+静态时间轴

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| graph.stream 后台化改动大 | PipelineRunner 复用现有 `_run_graph_streaming` 的节点事件逻辑，仅把 yield 改为写队列+快照 |
| 后端重启 running 会话悬挂 | 启动时扫描 status=running 置 failed（MVP），文档说明 |
| 轮询增加请求 | 仅切回的 running 会话轮询，2s 间隔，完成即停 |
| 快照与事件不一致 | 快照为单一恢复源，事件队列仅在线推送，二者由同一后台 task 产生 |
