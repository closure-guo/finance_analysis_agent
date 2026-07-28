## 1. 前端：类型定义 -- TimelineItem 联合类型

- [x] 1.1 编写失败测试：`TimelineItem` 联合类型三种 item 的结构校验（thinking / search / tool_call）
- [x] 1.2 `frontend/src/types.ts` 新增 `TimelineItem` 联合类型（thinking / search / tool_call 三种）
- [x] 1.3 `UIMessage` 新增 `agentTimeline: TimelineItem[]` 字段，废弃 `thinkingContent` / `thinkingTitle` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls` 分离字段
- [x] 1.4 更新 `ChatHistoryEntry` 类型（若后端 `chat_history` 结构不变，仅前端重建逻辑变化，类型可能无需改动）

## 2. 前端：事件处理 -- 写入 agentTimeline

- [x] 2.1 编写失败测试：`handleChatStreamEvent` 中 `thinking_token` 事件 -- 末尾是 thinking item 则累加，否则新建 thinking item
- [x] 2.2 编写失败测试：思考片段断开 -- `tool_call` 事件后再收 `thinking_token`，应新建 thinking item（不累加到旧 item）
- [x] 2.3 编写失败测试：`search_start` 事件新建 search item，`search_result` 更新该 item status/results，`search_error` 更新 status='error'
- [x] 2.4 编写失败测试：`tool_call` 事件新建 tool_call item（非搜索类工具），`tool_result` 更新对应 item（同名优先、回退最近未完成、无匹配新建）
- [x] 2.5 编写失败测试：`chat_done` 事件时所有 thinking item 用 `extractThinkingTitle` 提取标题写入 `title`
- [x] 2.6 实现 `handleChatStreamEvent` 改写：所有事件写入 `agentTimeline`（含思考片段断开逻辑、搜索/工具调用 item 创建与更新）
- [x] 2.7 实现 `handleSSEEvent`（管线模式）改写：`thinking_token` 按 `node` 字段写入对应 agent 阶段的 timeline
- [x] 2.8 历史会话恢复 `selectSession`：从 `chat_history.thinking` + `tool_calls` 重建 `agentTimeline`（思考在前、工具调用在后），每个 thinking item 用 `extractThinkingTitle` 提取标题

## 3. 前端：渲染 -- MessageRenderer 遍历 agentTimeline

- [x] 3.1 编写失败测试：chat 类型消息按 `agentTimeline` 数组顺序渲染（思考 -> 搜索 -> 工具调用 -> 思考 -> ... 的时序）
- [x] 3.2 编写失败测试：每个 thinking item 渲染为独立 ThinkingBanner（独立折叠状态、独立标题）
- [x] 3.3 编写失败测试：每个 search item 渲染为独立 SearchBanner
- [x] 3.4 编写失败测试：每个 tool_call item 渲染为独立 ToolCallBanner（单条目）
- [x] 3.5 编写失败测试：`chatResponse` 在所有横幅之后渲染，不被框体包裹
- [x] 3.6 实现 `MessageRenderer` chat 分支改写：遍历 `agentTimeline` 按 type 分发渲染（ThinkingBanner / SearchBanner / ToolCallBanner 复用现有组件）
- [x] 3.7 ToolCallBanner 适配单条目渲染（接收 `toolCalls={[item]}`，保持组件签名不变）

## 4. 前端：管线模式 -- 按 agent 阶段分组

- [x] 4.1 编写失败测试：管线模式按 agent 阶段分组 timeline（角色名标题分隔，阶段内时间序列）
- [x] 4.2 编写失败测试：并行 4 分析师的 timeline 按 `node` 字段分组
- [x] 4.3 实现 `PipelineCard` 改写：保留阶段进度条，每阶段内按时间序列渲染该 agent 的 timeline items，阶段间用角色名标题分隔（非折叠框）
- [x] 4.4 确认 `thinking_token` 事件 `node` 字段的实际取值（查阅后端 `src/finance_agent/` 事件定义）

## 5. E2E 与人工验证

- [x] 5.1 E2E 测试：快速模式输入 query，验证时间序列展示（思考 -> 搜索 -> 再思考 -> response），response 不框起（禁止 mock，通过前端模拟真实输入）
- [x] 5.2 E2E 测试：多段思考独立横幅（思考被工具调用断开后，每段独立横幅、独立标题、独立折叠）
- [x] 5.3 E2E 测试：搜索横幅在时间序列中的位置（穿插在思考片段之间）
- [x] 5.4 E2E 测试：深度模式澄清阶段时间序列展示
- [x] 5.5 E2E 测试：管线模式按 agent 阶段分组 timeline，阶段内时间序列
- [x] 5.6 E2E 测试：历史会话恢复后 agentTimeline 重建（思考/工具调用按近似时序排列，标题提取）
- [x] 5.7 E2E 测试：横幅折叠/展开交互（每个横幅独立折叠状态）
- [x] 5.8 人工验证报告落 `tests/validation/`，覆盖时间序列展示截图、多段思考独立横幅截图、管线模式分组截图、历史恢复截图
- [x] 5.9 `openspec validate agent-turn-box-display` 通过

## 6. 清理 -- 移除废弃字段相关代码

- [x] 6.1 移除 `UIMessage` 中废弃的分离字段（`thinkingContent` / `thinkingTitle` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls`）及其所有引用
- [x] 6.2 移除 `isSearchTool` 过滤逻辑中不再需要的分支（若有）
- [x] 6.3 移除 `MessageRenderer` 中固定 JSX 顺序的旧代码（SearchBanner -> ToolCallBanner -> ThinkingBanner）
- [x] 6.4 `uv run pytest` 全量测试通过（前端单元测试 + 后端测试）
- [x] 6.5 `uv run ruff check` 与 `cd frontend && npm run lint`（若有）通过
