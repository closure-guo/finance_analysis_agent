## Why

终态事件（done/interrupted/error）的 CAS 去重作用域错误地覆盖整个会话 journal 历史。第一轮结束后 journal 中已存在 `done`，第二轮起所有终态事件被 `has_terminal_event` 判定为"已有终态"而丢弃（返回 0，不入 journal、不 fan-out）。前端永远收不到第二轮的终态事件，导致流式游标永久卡死、停止按钮失效、error 事件不下发。CAS 的本意仅是防止同一轮运行内"显式 done + `_run_task` 自动 done"重复发送，不应跨轮次生效。

## What Changes

- **后端（治本）**：将终态事件 CAS 从"查 journal 全历史"改为 per-run 内存标志。`SessionStream` 新增 `terminalPublished: bool`，`start()` 时天然为 False（每次新建实例），`publish()` 发布终态事件时检查并置位；任务注销后流对象销毁，下一轮 `start()` 天然是新标志位。移除 `session_store.has_terminal_event()` 的调用（保留函数以备其他用途或删除）。
- **前端（纵深防御）**：
  - `startAnalysis` 的 SSE 循环补上 `chat_done` 分支，路由到 `handleChatStreamEvent`（与 `quickChat` 对齐），使 `applyChatStreamEvent` 在 `chat_done` 时将 `streaming` 置为 false。
  - 三处"流结束但未收到终态事件"的防御性清理（reader done / catch 块），追加将最后一条助手消息 `streaming` 置 false，避免游标依赖单一终态事件。
- **测试**：后端新增 per-run CAS 单元测试（两轮 publish 终态事件，第二轮不被吞）；前端新增 Vitest 模拟 SSE 流在缺少 `done` 的情况下结束，断言游标消失。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `session-streaming`: 终态事件 CAS 去重的作用域从"会话 journal 全历史"改为"单次运行 per-run 标志"，明确同一会话多轮追问时每轮独立发送终态事件。
- `frontend`: `startAnalysis` SSE 循环补齐 `chat_done` 事件路由；流结束防御性清理追加 `streaming: false` 兜底，使游标不依赖单一终态事件。

## Impact

- **后端代码**：`src/finance_agent/stream_registry.py`（`SessionStream` dataclass、`publish()` CAS 逻辑）、`src/finance_agent/session_store.py`（`has_terminal_event` 不再被 publish 调用）。
- **前端代码**：`frontend/src/App.tsx`（`startAnalysis` SSE 循环 `chat_done` 分支、防御性清理 `streaming: false`）。
- **API 契约**：无变化——SSE 事件类型与格式不变，仅修复第二轮起终态事件实际下发的行为。
- **数据库**：无 schema 变更。
- **测试**：后端 `tests/` 新增 per-run CAS 测试；前端 `frontend/src/test/` 新增 Vitest 游标消失测试。
