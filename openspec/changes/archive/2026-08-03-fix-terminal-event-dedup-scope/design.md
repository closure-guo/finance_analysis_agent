## Context

终态事件（done/interrupted/error）的 CAS 去重在 `StreamRegistry.publish()` 中实现，依赖 `session_store.has_terminal_event()` 扫描整个会话 journal 历史判断是否已有终态事件。该实现导致同一会话多轮追问时，第一轮的 `done` 残留在 journal 中，第二轮起的终态事件被 CAS 判定为"已有终态"而丢弃（返回 0，不入 journal、不 fan-out）。前端永远收不到第二轮终态事件，游标永久卡死。

CAS 的设计本意是防止同一轮运行内"生成逻辑显式发 done + `_run_task` 自动发 done"重复发送，作用域应为单次运行（per-run），不应跨轮次生效。

当前代码结构：
- `SessionStream` dataclass（`stream_registry.py:34-40`）：每次 `start()` 新建实例，任务结束后 `_notify_and_cleanup` 从 registry 注销。
- `publish()` CAS（`stream_registry.py:98-103`）：终态事件调用 `has_terminal_event` 查 journal 全历史。
- `has_terminal_event`（`session_store.py:315-334`）：`SELECT event_json FROM session_events WHERE session_id=? ORDER BY seq DESC` 扫描全量，遇终态类型返回 True。
- 前端 `startAnalysis` SSE 循环（`App.tsx:845-994`）：无 `chat_done` 分支；防御性清理（`App.tsx:1000-1006`）仅清 `streamingSessionIdRef`，未设 `msg.streaming: false`。

## Goals / Non-Goals

**Goals:**
- 后端终态事件 CAS 改为 per-run 内存标志，使同一会话每轮独立发送终态事件。
- 前端 `startAnalysis` SSE 循环补齐 `chat_done` 路由，与 `quickChat` 对齐。
- 前端流结束防御性清理追加 `streaming: false` 兜底，使游标不依赖单一终态事件。

**Non-Goals:**
- 不改变 SSE 事件类型与格式（API 契约不变）。
- 不改变 journal 持久化结构（无 schema 变更）。
- 不重构 `has_terminal_event` 函数（保留，不再被 `publish` 调用；若确认无其他调用方则删除）。
- 不处理恢复端点（`GET /api/sessions/{id}/stream`）的终态事件下发逻辑（该路径不走 `publish` CAS，不受此 bug 影响）。

## Decisions

### D1: per-run `terminalPublished` 标志（方案 A）替代 journal 全历史扫描

**决策**：`SessionStream` dataclass 新增 `terminalPublished: bool = False` 字段。`publish()` 发布终态事件时检查该标志：已为 True 则返回 0（同轮内去重），否则置 True 并正常写入。`start()` 每次新建 `SessionStream` 实例，标志天然为 False；任务注销后流对象销毁，下一轮 `start()` 天然是新标志。

**理由**：
- CAS 本意是防止同一轮运行内重复终态（显式 done + `_run_task` 自动 done），作用域本就是 per-run。
- `SessionStream` 已是 per-run 生命周期对象（`start()` 新建、`_notify_and_cleanup` 注销），标志位天然随运行重置，无需额外清理逻辑。
- 内存标志检查 O(1)，无需 SQL 查询和 JSON 反序列化，性能更优。

**备选方案 B（已否决）**：`has_terminal_event` 只检查"最后一条终态事件之后是否有新终态"（按轮次判定）。SQL 实现绕（需反向扫描找到最后终态后再确认无更晚终态），不如 per-run 标志干净，且仍依赖 journal 持久化状态而非运行时状态。

### D2: `startAnalysis` SSE 循环补齐 `chat_done` 路由

**决策**：在 `startAnalysis` 的 SSE 事件循环中，`chat_done` 事件路由到 `handleChatStreamEvent(event, assistantMsgIdRef.current)`，与 `quickChat` 对齐。`applyChatStreamEvent` 的 `chat_done` 分支会将 `streaming` 置为 false 并收口所有 thinking item。

**理由**：`handleChatStreamEvent` 已声明为两模式共享的事件处理函数（spec "Conversation Stream Common Events"），`chat_done` 已在其 switch 中（`App.tsx:1175`），但 `startAnalysis` 循环未将 `chat_done` 路由进去，导致深度模式澄清阶段的 `chat_done` 被静默丢弃。

### D3: 流结束防御性清理追加 `streaming: false`

**决策**：在 `startAnalysis` SSE 循环的三处"流结束但未收到终态事件"防御性清理点（reader done 后 `App.tsx:1000-1006`、catch 块 `App.tsx:1007-1021`），追加将 `assistantMsgIdRef.current` 对应的助手消息 `streaming` 置为 false。

**理由**：后端 CAS 修复后终态事件应能正常下发，但纵深防御要求游标不依赖单一事件。若因任何原因（网络中断、后端异常等）流结束而前端未收到终态事件，游标应自动消失而非永久卡死。

## Risks / Trade-offs

- **[风险] per-run 标志在进程重启后丢失** -> 不影响：进程重启后 `SessionStream` 本就不存在，`start()` 新建实例标志为 False；恢复端点不走 `publish` CAS，直接向订阅者发终态事件，不受影响。
- **[风险] `has_terminal_event` 删除后其他调用方报错** -> 缓解：修改前先全局搜索调用方；若仅有 `publish` 调用则安全删除，否则保留函数仅移除 `publish` 中的调用。
- **[风险] 前端 `chat_done` 路由可能与 `done` 终态事件重复设 `streaming: false`** -> 不影响：`streaming: false` 是幂等操作，重复设置无副作用。
- **[权衡] 防御性清理可能掩盖后端终态事件丢失的其他 bug** -> 可接受：防御性清理仅设 `streaming: false`（UI 层面），不影响 journal 持久化和事件日志完整性；后端事件丢失应通过日志和 Langfuse trace 独立排查。
