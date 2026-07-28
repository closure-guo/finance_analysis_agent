## Context

当前前端（`frontend/src/App.tsx`）将助手消息内的思考、搜索、工具调用按固定类型顺序渲染（Search -> ToolCall -> Thinking -> Response），由 `MessageRenderer` chat 分支的 JSX 顺序决定。`UIMessage` 用分离字段存储：`thinkingContent` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls`。这导致：
1. 思考被合并为一个横幅，显示在搜索/工具下面，与 SSE 事件到达的真实时序不符
2. 多次工具调用穿插在多段思考之间时，无法保留"思考1 -> 搜索 -> 思考2"的推理链路

Kimi 的时序体验是按 agent 实际执行顺序展示：思考 -> 搜索 -> 再思考 -> 回答，思考可能被工具调用断成多段，每段独立展示。

### 现有实现关键点

- `UIMessage.thinkingContent?: string`（单字符串，所有思考合并）
- `UIMessage.searchStatus?: 'searching'|'done'|'error'`，`searchQuery?: string`，`searchResults?: Array<{title,url,content}>`
- `UIMessage.toolCalls?: ToolCallEntry[]`（数组，所有工具调用合并到一个 ToolCallBanner）
- `MessageRenderer` chat 分支固定 JSX 顺序：SearchBanner -> ToolCallBanner -> ThinkingBanner -> chatResponse
- SSE 事件处理（`handleChatStreamEvent` / `handleSSEEvent`）将事件写入对应分离字段

## Goals / Non-Goals

**Goals:**

- 助手消息内的思考/搜索/工具调用按 SSE 事件到达的真实时序纵向排列
- 思考可能被工具调用断成多段，每段思考独立成 TimelineItem，独立提取标题
- 每个 timeline item 渲染为对应独立可折叠横幅（复用现有 ThinkingBanner / SearchBanner / ToolCallBanner）
- response 在 timeline 之后，Markdown 渲染，不框起
- 管线模式按 agent 阶段分组，阶段内按时间序列排列
- 历史会话恢复时重建 timeline

**Non-Goals:**

- 不改后端 SSE 事件协议（`thinking_*` / `search_*` / `tool_call` / `tool_result` 事件结构不变）
- 不改 ThinkingBanner / SearchBanner / ToolCallBanner 组件的内部展示逻辑（标题提取、折叠行为、搜索结果卡片等复用现有）
- 不改管线阶段进度条
- 不改报告卡片渲染
- 不引入外层 Agent 汇总折叠框（已确认取消，改为按动作独立横幅）

## Decisions

### 决策 1：数据结构 -- `agentTimeline: TimelineItem[]` 按事件时序追加

**选择**：`UIMessage` 新增 `agentTimeline: TimelineItem[]` 数组，废弃分离字段。SSE 事件到达时按序追加 TimelineItem。

```typescript
type TimelineItem =
  | { type: 'thinking'; content: string; title?: string }
  | { type: 'search'; query: string; results?: Array<{title,url,content}>; status: 'searching'|'done'|'error' }
  | { type: 'tool_call'; name: string; args: string; result?: string; done: boolean }
```

**理由**：
- 数组天然保序，符合 SSE 事件流式到达的特性
- 联合类型清晰表达三种 item 的数据结构
- 废弃分离字段避免"同一份数据两处维护"的一致性问题

**替代方案**：
- 保留分离字段，渲染时按事件时间戳排序 -> 否决，需给每个字段加时间戳，且思考被断开时一个 `thinkingContent` 字符串无法表达多段
- 用 Map/对象按 key 存 -> 否决，Map 无序（或需额外排序字段），数组最自然

### 决策 2：思考片段断开逻辑 -- 遇 tool_call / search_start 断开

**选择**：`thinking_token` 事件到达时，若 `agentTimeline` 末尾是 `thinking` 类型 item，则累加到该 item 的 `content`；否则（末尾是 search/tool_call，或 timeline 为空）新建一个 `thinking` item 追加。即"同一段思考流式累加，遇到工具调用/搜索事件则断开成新思考片段"。

**理由**：
- 符合 agent 实际执行模式：思考 -> 工具调用 -> 根据工具结果再思考 -> ...
- 每段思考独立成 item，独立提取标题，独立折叠，符合"每个动作独立横幅"的设计
- 实现简单：只需检查 `agentTimeline[agentTimeline.length-1].type`

**替代方案**：
- 所有思考合并为一个 item，内部用分隔符区分段落 -> 否决，无法独立提取每段标题，且与"每个动作独立横幅"设计冲突
- 按固定窗口断开（如每 N 个 token）-> 否决，无业务意义

### 决策 3：渲染 -- 遍历 agentTimeline 按 type 分发到对应横幅组件

**选择**：`MessageRenderer` chat 分支从固定 JSX 顺序改为遍历 `agentTimeline`，按 `item.type` 分发：

```tsx
{msg.agentTimeline?.map((item, i) => {
  if (item.type === 'thinking') return <ThinkingBanner key={i} content={item.content} title={item.title} streaming={...} />
  if (item.type === 'search') return <SearchBanner key={i} status={item.status} query={item.query} results={item.results} />
  if (item.type === 'tool_call') return <ToolCallBanner key={i} toolCalls={[item]} streaming={...} />  // 单条目
})}
{msg.chatResponse && <ReactMarkdown>{msg.chatResponse}</ReactMarkdown>}
```

**理由**：
- 复用现有 ThinkingBanner / SearchBanner / ToolCallBanner 组件，内部展示逻辑不变
- 遍历数组天然按时序渲染
- ToolCallBanner 接收单条目数组（`[item]`），保持组件签名不变（现有组件接收 `ToolCallEntry[]`），最小改动

**替代方案**：
- 改造 ToolCallBanner 接收单条目 -> 可考虑，但保持数组签名更兼容，且未来若需"同一 agent 内连续多个 tool_call 合并展示"可在外层聚合

### 决策 4：ToolCallBanner 粒度 -- 每次 tool call 一个独立横幅实例

**选择**：每次 tool call 作为一个独立 TimelineItem，渲染为一个独立的 ToolCallBanner 实例（单条目）。不再将所有 tool call 合并到一个横幅。

**理由**：
- 与"每个动作独立横幅"设计一致
- 时间序列下，多次 tool call 穿插在多段思考之间，合并成一个横幅会破坏时序
- 现有 ToolCallBanner 组件支持单条目数组，无需改组件

**替代方案**：
- 连续多个 tool_call 合并为一个横幅 -> 否决，增加"连续性判断"复杂度，且与 Kimi 风格不符（Kimi 每次工具调用独立展示）

### 决策 5：标题展示 -- 每段思考独立提取，沿用 thinking-stream-banner-display 规则

**选择**：每个 `thinking` 类型的 TimelineItem 独立用 `extractThinkingTitle(item.content)` 提取标题，存入 `item.title`。展示规则沿用 `thinking-stream-banner-display`：
- 流式中：横幅标题"思考中"（脉冲动画）
- 完成折叠 + 有标题：显示标题
- 完成折叠 + 无标题：显示"思考已完成"
- 完成展开：横幅固定"思考已完成"，框内标题加粗置顶（若有）

**理由**：
- 与已实现的 `thinking-stream-banner-display` 行为一致，复用 `extractThinkingTitle` 工具函数
- 每段思考独立标题，用户折叠状态下可看到每段思考的主题

### 决策 6：管线模式 -- 按 agent 阶段分组，阶段内时间序列

**选择**：管线模式保留阶段进度条。每个 agent 阶段（多头分析师 / 空头分析师 / Trader 等）的 timeline items 归在该阶段下，阶段间用角色名标题分隔（非折叠框，纯文本标题）。阶段内按时间序列排列该 agent 的思考/搜索/工具调用横幅。

**理由**：
- 管线有多个 agent，需要区分每个 agent 的 timeline，角色名标题提供分隔
- 阶段内仍是时间序列，保留每个 agent 的推理链路
- 非折叠框，避免嵌套折叠的复杂度

**替代方案**：
- 管线模式也用扁平时间序列（所有 agent 的 timeline 混在一起）-> 否决，多 agent 时无法区分谁的思考/工具调用
- 每个 agent 阶段用可折叠汇总框 -> 否决，与"取消外层汇总框"的设计决策冲突

### 决策 7：历史会话恢复 -- 重建 agentTimeline

**选择**：`selectSession` 从 `chat_history` 恢复时，将 `thinking` + `tool_calls` 重建为 `agentTimeline`。由于 `chat_history` 当前是 `thinking`（单字符串）+ `tool_calls`（数组）分离存储，恢复时无法精确还原时序，采用启发式：`thinking` 作为一个 thinking item，`tool_calls` 按序作为 tool_call items，按"思考在前、工具调用在后"的顺序排列（或根据后端存储的时序字段，若有）。

**理由**：
- 历史数据本身没有完整时序信息（thinking 是合并后的字符串），只能近似还原
- 实时流式是主要场景，历史恢复的时序偏差可接受
- 若后端 `chat_history` 未来增强为时序存储，可无缝升级

**风险**：历史恢复的时序可能与真实执行时序不一致 -> 可接受，实时流式场景不受影响；若需精确时序，需后端 `chat_history` 增强存储 timeline 结构（后续迭代）

### 决策 8：search 事件与 tool_call 事件的关系 -- search 独立成 item，不进 tool_call

**选择**：`web_search` / `batch_web_search` 的 `search_start` / `search_result` / `search_error` 事件生成 `search` 类型 TimelineItem，不生成 `tool_call` item。其他工具的 `tool_call` / `tool_result` 事件生成 `tool_call` item。

**理由**：
- 沿用现有 `isSearchTool` 过滤逻辑，搜索由 SearchBanner 承载，展示"搜索了 N 个网页"等搜索特有 UI
- 搜索结果卡片（favicon / 标题 / 摘要 / 域名）与通用 tool call 的"参数/结果"展示不同，分开合理

## Risks / Trade-offs

- **[历史恢复时序不准确]** `chat_history` 分离存储 thinking + tool_calls，恢复时无法精确还原时序 -> 可接受，实时流式场景不受影响；后续可增强后端存储 timeline 结构
- **[timeline 数组频繁更新性能]** 流式时每 token 触发 `agentTimeline` 数组更新（新建数组）-> 可接受，React 状态更新常态；若性能问题可用 useMemo/节流优化，属实现细节
- **[思考片段断开边界]** 若 agent 连续输出思考而未调用工具，所有思考合并为一个 item（符合预期）；若工具调用后 agent 未再思考直接回答，则最后一段思考后无新 thinking item（符合预期）
- **[ToolCallBanner 单条目样式]** 现有 ToolCallBanner 设计为"已调用工具 · N 次"汇总样式，单条目时显示"已调用工具 · 1 次"可能冗余 -> 可接受，或微调文案为"已调用工具"（去掉次数），属实现细节

## Migration Plan

- 前端类型：`UIMessage` 新增 `agentTimeline: TimelineItem[]`，废弃分离字段（`thinkingContent` / `thinkingTitle` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls`）
- 前端事件处理：`handleChatStreamEvent` / `handleSSEEvent` 改写为向 `agentTimeline` 追加 TimelineItem（含思考片段断开逻辑）
- 前端渲染：`MessageRenderer` chat 分支改为遍历 `agentTimeline` 渲染
- 管线 UI：`PipelineCard` 按 agent 阶段分组 timeline
- 历史恢复：`selectSession` 重建 `agentTimeline`
- 测试：单元测试覆盖 timeline 构建/断开/历史恢复；E2E 覆盖两种模式的时间序列展示
- 回滚：还原 `UIMessage` 类型 + 事件处理 + 渲染逻辑即可

## Open Questions

- 历史恢复时 `chat_history.thinking`（合并字符串）与 `tool_calls`（数组）的时序还原策略：按"思考在前、工具调用在后"固定顺序，还是根据后端是否有额外时序字段？倾向：先按固定顺序近似还原，后续后端增强时再精确化。具体在 tasks 实现阶段确认后端 `chat_history` 实际结构。
- 管线模式并行 4 分析师的 timeline 展示：4 个分析师并行执行，各自的 timeline 如何与 SSE 事件流对应（`thinking_token` 事件的 `node` 字段区分）？具体在 tasks 实现阶段确认 `node` 字段的实际取值。
