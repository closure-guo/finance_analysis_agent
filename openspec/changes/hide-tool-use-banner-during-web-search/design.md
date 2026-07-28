## Context

当前前端对话流中，当 Agent 调用 `web_search` / `batch_web_search` 工具时，后端为同一次搜索行为下发两类 SSE 事件：

- 通用 `tool_call` / `tool_result` 事件 -> 追加到助手消息 `toolCalls` 数组 -> 触发 **ToolCallBanner**（"调用工具中 · N 次"）
- 专用 `search_start` / `search_result` 事件 -> 写入 `searchStatus` / `searchResults` -> 触发 **SearchBanner**（"正在搜索：xxx" / "搜索了 N 个网页"）

`MessageRenderer` 中两个横幅是两个独立的 `{cond && <Comp/>}` 表达式，无任何互斥判断，导致同一次搜索同时出现两个横幅。根因不在后端事件冗余（事件各自承载不同语义：通用 vs 结构化），而在前端消费侧未对搜索类工具做分流过滤。

## Goals / Non-Goals

**Goals:**

- 消除搜索类工具调用时 SearchBanner 与 ToolCallBanner 的重复展示
- 保持 `search_stock` 等非搜索类工具的现有工具调用横幅行为不变
- 保持搜索横幅与非搜索工具横幅在并存时各自独立展示（各自承载不同语义）
- 历史会话恢复时同步过滤搜索类工具，避免历史会话仍显示重复横幅

**Non-Goals:**

- 不改动后端 SSE 事件流（`tool_call` / `tool_result` / `search_*` 仍照常下发）
- 不改动 SearchBanner 组件本身的展示样式与三态切换逻辑
- 不处理 `search_stock` 工具（它仍由工具调用横幅展示，与搜索横幅无关）
- 不改动深度分析管线 UI（`run_deep_analysis` 的分流逻辑保持不变）
- 不做数据迁移（历史会话中已存的搜索类 tool_calls 记录将被过滤，符合预期）

## Decisions

### 决策 1：过滤点放在前端消费侧，而非后端不下发

**选择**：在前端 `handleChatStreamEvent` 处理 `tool_call` 事件时，对 `web_search` / `batch_web_search` 跳过 `toolCalls` 追加。

**理由**：后端事件流被前端多处消费（对话流、管线、可能的未来消费者），改动后端会影响面广且违背"事件各自承载不同语义"的设计。前端过滤改动面小、风险低、可回退。

**替代方案**：后端不为搜索类工具下发 `tool_call` 事件 -> 否决，会丢失通用工具调用追踪（如 Langfuse 链路对齐），且后端事件下发与前端展示耦合。

### 决策 2：过滤点集中在共用的 `handleChatStreamEvent` 内部

**选择**：在 `handleChatStreamEvent` 的 `tool_call` case（App.tsx 第 741-750 行）与 `tool_result` case（第 752-777 行）开头，对 `web_search` / `batch_web_search` 直接 `return true` 跳过，不追加 `toolCalls`、不附加结果、不新建记录。

**理由**：`handleChatStreamEvent` 是深度模式（`startAnalysis`）与快速模式（`quickChat`）共用的事件处理器——深度模式在 tool_call 分流处（第 439 行）把非 `run_deep_analysis` 事件转入它，快速模式（第 875 行）直接把所有事件交给它。在此处过滤可**一处改动同时覆盖两种模式**，改动点最少（2 处 case + 历史恢复 1 处）。

**替代方案**：在深度模式 `startAnalysis` 的 tool_call 分流处（第 433-442 行）与 `run_deep_analysis` 并列拦截 -> 否决，快速模式 `quickChat` 无此分流点（直接调用 `handleChatStreamEvent`），会漏掉快速模式的搜索场景。

### 决策 3：`tool_result` 对搜索类工具不新建记录

**选择**：在 `handleChatStreamEvent` 的 `tool_result` 处理中，若事件对应 `web_search` / `batch_web_search`，不附加到任何记录、不新建记录。

**理由**：搜索类工具不进入 `toolCalls` 后，`tool_result` 若按现有回退逻辑（"无同名未完成记录 -> 回退到最近未完成的任意工具调用"）会错误地把搜索结果附加到其他工具；且"无任何匹配记录且结果非空 -> 新建一条仅含结果的记录"会让搜索类工具重新进入 `toolCalls`，绕过过滤。搜索结果已由 `search_result` 事件驱动搜索横幅，`tool_result` 对搜索类工具是冗余的。

### 决策 4：历史会话恢复同步过滤

**选择**：在 `selectSession` 调用 `buildToolCallEntry` 还原 `tool_calls` 时，过滤 `web_search` / `batch_web_search`。

**理由**：保证实时流和历史会话展示一致，避免历史会话仍出现重复横幅。

## Risks / Trade-offs

- **[历史会话展示变化]** 历史会话中已存的搜索类 tool_calls 记录将不再显示工具横幅条目 -> 可接受，搜索横幅本就是更优的展示形态；且历史会话通常不重建 searchStatus，过滤后该消息可能既无搜索横幅也无搜索工具横幅条目，但思考横幅与回答仍正常展示，不影响信息完整性。
- **[过滤清单维护]** 若未来新增其他搜索类工具，需同步更新过滤判断 -> 可接受，过滤判断集中在一处（`tool_call` 分流点）+ 一处（`tool_result` 处理）+ 一处（历史恢复），易维护；可在 `buildToolCallEntry` 旁提取常量集合 `SEARCH_TOOL_NAMES`。
- **[tool_result 与 search_result 时序]** 若 `tool_result` 先于 `search_result` 到达，搜索类工具已被跳过，不会产生残留记录 -> 无风险，设计上即不依赖 `tool_result`。

## Migration Plan

- 纯前端变更，无数据迁移、无后端发布
- 部署即生效：新发起的对话流立即遵循新过滤逻辑；加载历史会话时同步过滤
- 回滚策略：还原 `frontend/src/App.tsx` 三处改动即可
