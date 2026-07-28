## Why

当前前端将助手消息内的思考、搜索、工具调用按固定类型顺序渲染（Search -> ToolCall -> Thinking -> Response，见 `App.tsx` MessageRenderer chat 分支），不是按 SSE 事件到达的真实时序。这与 Kimi 的时序体验不一致：Kimi 按 agent 实际执行顺序展示（思考 -> 搜索 -> 再思考 -> 回答），思考可能被工具调用断成多段，每段独立展示，保留完整推理链路。金融分析场景下推理时序透明度尤为重要——用户需要看到"先想到什么 -> 去搜了什么 -> 又想到什么 -> 得出什么结论"的完整链路，而非被合并后的分类汇总。

## What Changes

- **BREAKING**：助手消息内的思考/搜索/工具调用从固定类型顺序改为时间序列，按 SSE 事件到达顺序纵向排列
- **BREAKING**：`UIMessage` 数据结构从分离字段（`thinkingContent` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls`）改为 `agentTimeline: TimelineItem[]` 数组，按事件时序追加
- **TimelineItem 联合类型**：`{type:'thinking', content, title?}` 思考片段（被工具调用断开的多段思考各自独立）| `{type:'search', query, results, status}` 搜索 | `{type:'tool_call', name, args, result, done}` 其他工具调用
- **渲染**：按 `agentTimeline` 数组顺序渲染，每个 timeline item 渲染为对应独立可折叠横幅（ThinkingBanner / SearchBanner / ToolCallBanner 复用现有组件，每个 timeline item 一个横幅实例）
- **思考片段断开**：同一段思考流式累加，遇到 `tool_call` / `search_start` 事件则断开成新思考片段（新 TimelineItem）
- **标题展示**：每段思考独立用 `extractThinkingTitle` 提取标题，沿用 `thinking-stream-banner-display` 的展示规则（思考中脉冲 / 思考已完成 / 折叠显标题 / 展开固定"思考已完成"+置顶加粗）
- **工具执行期间状态文案**：web search 执行期间 SearchBanner 显示"正在搜索网页"、其他工具执行期间 ToolCallBanner 显示"正在调用工具"，不再一律显示"思考中"；思考横幅仅在 agent 实际思考（timeline 末尾为 thinking item）时显示"思考中"，工具执行期间不显示"思考中"
- **Response**：在 timeline 之后，Markdown 渲染，不框起
- **管线模式**：保留阶段进度条；每个 agent 阶段内按时间序列排列该 agent 的 timeline items（思考/搜索/工具调用横幅），阶段间用角色名标题分隔（非折叠框）
- **历史会话恢复**：从 `chat_history` 恢复时重建 `agentTimeline`（思考与工具调用按时序还原）

## Capabilities

### New Capabilities

（无--时间序列作为 `frontend` capability 下的新 Requirement，不单独建 capability）

### Modified Capabilities

- `frontend`：新增 `Agent Timeline Display` 需求（定义时间序列数据结构、timeline item 渲染规则、思考片段断开逻辑、标题展示、对话/管线两种模式的渲染规则）；修改 `Thinking Banner Display`、`Tool Call Banner Display`、`Quick Chat Search Events`、`Deep Mode Search Banner`、`Pipeline Thinking Display`、`Conversation Stream Common Events`、`Message Type Rendering`、`Chat History Restore With Tool Calls` 等需求，将固定类型顺序改为时间序列

## Impact

- **前端类型**（`frontend/src/types.ts`）：`UIMessage` 新增 `agentTimeline: TimelineItem[]` 字段，废弃 `thinkingContent` / `thinkingTitle` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls` 分离字段；新增 `TimelineItem` 联合类型（`thinking` / `search` / `tool_call` 三种）
- **前端渲染**（`frontend/src/App.tsx`）：`MessageRenderer` chat 分支从固定 JSX 顺序改为遍历 `agentTimeline` 渲染；每个 timeline item 实例化对应横幅组件（ThinkingBanner / SearchBanner / ToolCallBanner 复用，按 type 分发）
- **前端事件处理**：`handleChatStreamEvent` 与 `handleSSEEvent` 中 `thinking_token` / `thinking_replace` / `thinking_to_answer` / `search_*` / `tool_call` / `tool_result` 事件的写入目标从分离字段改为 `agentTimeline` 数组按序追加；思考片段断开逻辑（遇 tool_call/search_start 断开当前思考片段）
- **管线 UI**：`PipelineCard` 内 timeline 按 agent 阶段分组，每阶段内按时间序列排列
- **历史会话恢复**：`selectSession` 构建 `UIMessage` 时从 `chat_history.thinking` + `tool_calls` 重建 `agentTimeline`
- **测试**：单元测试覆盖 timeline 构建、思考片段断开、搜索/工具调用按时序插入、历史恢复重建；E2E 覆盖对话模式与管线模式的时间序列展示、折叠交互、历史恢复（禁止 mock，通过前端模拟真实输入）
- **后端**：无改动--SSE 事件协议不变，`thinking_*` / `search_*` / `tool_call` / `tool_result` 事件结构不变，仅前端消费方式从分字段改为按序追加 timeline
