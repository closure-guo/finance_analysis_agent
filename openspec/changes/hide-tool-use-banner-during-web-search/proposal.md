## Why

当 Agent 调用 `web_search` / `batch_web_search` 工具时，后端同时下发两类 SSE 事件：
- 通用 `tool_call` / `tool_result` 事件 -> 追加到助手消息的 `toolCalls` 数组 -> 触发 **工具调用横幅（ToolCallBanner）**
- 专用 `search_start` / `search_result` 事件 -> 写入 `searchStatus` / `searchResults` -> 触发 **搜索横幅（SearchBanner）**

由于前端渲染层对两个横幅无任何互斥判断，同一次网页搜索会同时出现两个横幅（"调用工具中 · N 次" + "正在搜索：xxx"），信息重复、视觉冗余，用户难以快速识别 Agent 正在做什么。现有 `frontend` spec 分别定义了两个横幅的行为，却未约束二者并存时的展示规则，属于行为未定义。

## What Changes

- 当工具调用为 `web_search` 或 `batch_web_search` 时，该条目 SHALL NOT 进入 `toolCalls` 数组、SHALL NOT 在工具调用横幅中渲染，搜索信息仅由独立的搜索横幅（SearchBanner）展示。
- 非搜索类工具（如 `search_stock`）保持现有行为不变，仍记录到 `toolCalls` 并由工具调用横幅展示。
- 当一条助手消息同时存在搜索横幅（`searchStatus` 有效）与非搜索类 `toolCalls` 时，两个横幅仍可并存（各自承载不同语义，无信息重复）。
- 历史会话恢复（`selectSession`）时，`chat_history` 中的 `web_search` / `batch_web_search` 工具调用记录同样不还原到 `toolCalls` 横幅。

## Capabilities

### New Capabilities

<!-- 无新增 capability -->

### Modified Capabilities

- `frontend`: 新增"搜索类工具调用横幅互斥"需求，约束 `web_search` / `batch_web_search` 工具调用仅由搜索横幅展示、不进入工具调用横幅；并据此调整会话历史恢复逻辑

## Impact

- **前端代码**：`frontend/src/App.tsx`
  - `handleChatStreamEvent` 对 `tool_call` 事件的处理（当前第 741-750 行）：需对 `web_search` / `batch_web_search` 跳过 `toolCalls` 追加
  - `selectSession` 恢复 `chat_history` 时调用 `buildToolCallEntry` 的逻辑（当前第 185-187 行附近）：同样需过滤搜索类工具
  - `search_result` 事件处理中标记 toolCall `done: true` 的逻辑（当前第 459-464 行）：在搜索类工具不进入 `toolCalls` 后，此分支将自然失效，可一并清理
  - `MessageRenderer` 渲染条件无需改动（依赖 `toolCalls.length > 0`，过滤后自动满足）
- **测试**：
  - 单元测试：`frontend/src/test/SearchBanner.test.tsx` 既有覆盖；需新增 `tool_call` 事件分流测试，断言搜索类工具不进入 `toolCalls`
  - E2E：根据 `tests/e2e/` 约束，需通过前端真实操作验证只出现一个搜索横幅
- **后端**：无变更，后端仍正常下发 `tool_call` 与 `search_*` 事件，仅前端消费侧过滤
- **spec**：`openspec/specs/frontend/spec.md` 在 F 行为域（渲染与展示）新增互斥需求
