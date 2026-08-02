# Change: resume-stream-on-session-switch

## Why

切换会话后 Agent 输出无法继续，coding agent 多次修复无效。根因是架构性的，而非 UI 状态问题：

1. **生成任务生命周期绑定 HTTP 连接**：`/api/analyze` 与 `/api/chat` 把 ReAct Agent 循环直接跑在 `StreamingResponse` 的 async generator 内（`api.py:1024`、`agent_factory.py:695`）。前端 `selectSession` 调 `abortStreaming()` 断开 SSE 后，Starlette 向生成器抛 `CancelledError`，整个 Agent 循环被杀死。
2. **中断即丢数据**：assistant 回复在流结束后才 `append_chat` 落库（`api.py:1067`、`api.py:1178`），中断时 collector 中已生成的半截内容直接销毁；user 消息却在请求开始时就落库（`api.py:903`），留下无回答的悬空 user 消息，污染后续上下文。
3. **session 状态腐烂**：status 永远卡在 `clarifying`/`running`，无 `interrupted` 终态。
4. **无重连机制**：切回会话时 `selectSession` 只拉持久化快照，不存在"该会话还在跑就重连接续传"的路径。
5. **spec 固化了错误行为**：`frontend/spec.md` 的 `Session Selection` 与 `SSE Stream Abort Control` 两条 Requirement 明文规定"切换会话 SHALL 中断 SSE 流"——coding agent 按 spec 实现，每次"修复"都在重新引入 bug。

## What Changes

- **后端：生成与连接解耦**。`/api/analyze`、`/api/chat` 收到请求后以 `asyncio.create_task` 启动后台生成任务，任务持有者是 session 而非连接；SSE 端点退化为 per-session 事件队列的订阅转发者。客户端断开仅退订，不杀任务。
- **后端：事件日志（Event Journal）**。新增 `session_events` 表，每个 SSE 事件按 session 内单调递增 `seq` 落库，作为重放的事实源。
- **后端：可恢复流端点**。新增 `GET /api/sessions/{id}/stream?after_seq=N`，先按 seq 重放历史事件，再接续实时事件；支持 SSE 标准 `Last-Event-ID` 头。
- **后端：中断兜底持久化**。任务被取消/异常时，collector 已收集的部分回复落库并标注中断，session status 置为 `interrupted`；服务重启时将残留 `running` 会话 reconcile 为 `interrupted`。
- **后端：单会话单飞（single-flight）**。同一会话同一时间至多一个生成任务；运行中收到新消息返回 409 `session_busy`。新增 `POST /api/sessions/{id}/cancel` 显式取消。
- **前端：切换会话不再中断生成**（MODIFIED `Session Selection` / `SSE Stream Abort Control`）。切换仅退订 UI 渲染；流状态（pipeline、streamingReport）按 sessionId 存入 Map 而非全局单例 ref；选中运行中的会话时经恢复端点重连，内容继续增长。
- **前端：侧边栏运行指示**。运行中的会话显示"生成中"指示；显式"停止"按钮走 cancel 端点，abort 仅保留为页面卸载等边缘场景的兜底。
- **BREAKING（行为级）**：切换会话不再中断生成。依赖"切会话杀任务"隐式语义的用户行为消失，取消生成必须显式操作。

## Capabilities

### New Capabilities

- `session-streaming`：后端生成任务与 HTTP 连接解耦、事件日志持久化、可恢复流端点、中断兜底持久化、single-flight 与显式取消。

### Modified Capabilities

- `frontend`：`Session Selection` 改为"切换不杀任务、运行中会话重连续传"；`SSE Stream Abort Control` 收缩为"仅显式取消与页面卸载时中断"；新增按 sessionId 的流状态管理与运行指示。
- `e2e-core-specs`：新增"流式输出中途切换会话再切回，内容继续追加"的端到端场景。

## Impact

- **后端 API**（`api.py`）：`/api/analyze`、`/api/chat` 改为任务提交 + 订阅转发；新增 `GET /api/sessions/{id}/stream`、`POST /api/sessions/{id}/cancel`；`event_stream`/`chat_stream` 主体迁入后台任务。
- **后端新增模块**：`stream_registry.py`（per-session 任务句柄、订阅者队列、心跳、single-flight 判定）。
- **后端持久化**（`session_store.py`）：新增 `session_events` 表（session_id、seq、event_json、created_at）与迁移；status 枚举新增 `interrupted`；启动 reconcile。
- **后端 Agent 映射层**（`agent_factory.py`）：`stream_agent_to_sse` 的事件写入 registry/journal，不再直接面向 HTTP 响应。
- **前端**（`App.tsx`、`types.ts`）：`selectSession`/`newAnalysis`/`deleteSession` 移除 abort 语义；新增 `streamRegistry: Map<sessionId, StreamState>`；`abortRef` 改为 per-session；新增恢复端点订阅逻辑与侧边栏运行指示。
- **ADR**：需新增 ADR 记录"生成任务与 SSE 连接解耦 + 事件日志重放"的架构决策（手动维护，agent 不得自动新建）。
- **测试**：StubLLMClient 管线复用；新增后端单测（断连不杀任务、journal 重放、中断落库、single-flight 409）与 E2E（stub 管线中途切换会话再切回）。
- **部署约束**：registry 为进程内内存结构，限定单 uvicorn worker；多 worker/多副本部署不在本 change 范围（README/部署文档注明）。

## Non-goals

- 不做分布式任务队列（Celery/Redis 等）；事件日志仅为重放服务，不做长期事件溯源（event sourcing）改造。
- 不改动 LangGraph 5 层管线内部逻辑与 Langfuse 追踪结构。
- 不支持多标签页同时订阅同一会话的写冲突协调（多订阅者只读转发即可，写操作仍走单飞约束）。

## References

- 事故分析：本会话根因分析（生成绑定连接、持久化顺序、spec 固化错误行为）
- 相关 incident：`docs/incidents/012-sse-stream-tests-deselected-20260727.md`（SSE 生命周期缺乏可测试边界，同族问题）
- 现状代码：`src/finance_agent/api.py:854-1211`、`src/finance_agent/agent_factory.py:642-...`、`frontend/src/App.tsx:86-508`
- SSE 重连标准：HTML Server-Sent Events `Last-Event-ID` 语义
