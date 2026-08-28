# Session Persistence Specification

## Purpose

定义对话与管线时序的结构化持久化契约，确保思考/搜索/工具调用的真实交错时序在会话存储与恢复过程中不丢失。
## Requirements
### Requirement: 对话时序结构化持久化

系统 SHALL 将 assistant 消息的思考/搜索/工具调用按真实交错时序持久化到 `chat_history` 条目的 `agentTimeline` 字段（TimelineItem 数组），替代仅靠拍平 `thinking` 字符串的恢复。后端在流式消费时构建结构化时序，语义与前端 `applyChatStreamEvent` 等价。

TimelineItem 结构（与前端 `types.ts` 同构）：
- `{type:'thinking', content, title?, done?}`
- `{type:'search', query, results?, status}`
- `{type:'tool_call', name, args, result?, done}`

#### Scenario: assistant 消息持久化 agentTimeline

- **GIVEN** 一次分析/对话产生思考、搜索、工具调用的交错事件流
- **WHEN** 后端将该 assistant 消息写入 chat_history
- **THEN** 条目 SHALL 包含 `agentTimeline` 字段，按事件到达顺序记录 thinking/search/tool_call items
- **AND** thinking 片段在 search/tool_call 处断开为多段（与前端流式构建一致）
- **AND** 既有 `thinking`/`tool_calls` 字段保留（向后兼容）

#### Scenario: 旧会话无 agentTimeline 字段兼容

- **GIVEN** 历史 chat_history 条目仅有 thinking/tool_calls，无 agentTimeline
- **WHEN** 前端恢复该消息
- **THEN** 前端 SHALL 回退 buildTimelineFromHistory 近似重建，不报错

### Requirement: 管线时序持久化

系统 SHALL 将深度分析管线各节点的思考/工具时序持久化到 sessions 表 `pipeline_timelines` 列（JSON：`{node: [TimelineItem]}`），管线运行中按节点事件与 `pipeline_snapshot` 同节奏写入。

#### Scenario: 管线节点时序持久化

- **GIVEN** 深度分析管线运行中产生 thinking_token（含 node 字段）/工具/搜索事件
- **WHEN** 管线执行（fast path PipelineRunner 或 ReAct run_deep_analysis 工具）
- **THEN** 系统 SHALL 按 node 分组维护时序并写入 pipeline_timelines
- **AND** 节点完成时收口该节点末段 thinking（等价前端 applyPipelineNodeComplete）

#### Scenario: 会话详情返回管线时序

- **GIVEN** 某会话的 pipeline_timelines 已写入
- **WHEN** 前端请求 GET /api/sessions/{sessionId}
- **THEN** 响应 SHALL 包含 pipeline_timelines（可解析为 {node: [TimelineItem]}）

### Requirement: 管线触发锚点持久化

系统 SHALL 在深度分析管线启动时将触发锚点持久化到 sessions 表 `pipeline_anchor` 列（INTEGER，NULL 表示无锚点）。锚点 = 启动时刻 chat_history 中最后一条 role='user' 条目的索引 + 1，即"触发本轮分析的用户消息之后"，供前端历史重建时定位报告消息插入位置。

锚点 SHALL 在两条管线启动路径上写入：fast path（已知股票代码直接启动 PipelineRunner）与 ReAct 路径（run_deep_analysis 工具实际启动管线时）。锚定 user 消息而非取 chat_history 长度，避免 ReAct 路径 assistant 在途增量 upsert 导致锚点随持久化时机抖动。

#### Scenario: fast path 写入锚点

- **GIVEN** 新会话首次输入即解析出股票代码（fast path）
- **WHEN** 用户消息追加到 chat_history 后、管线启动前
- **THEN** 系统 SHALL 将 pipeline_anchor 写为 1（chat_history 仅一条 user 消息）
- **AND** 旧库启动时经幂等 ALTER TABLE 迁移添加 pipeline_anchor 列，既有行保持 NULL

#### Scenario: ReAct 路径写入锚点

- **GIVEN** 多轮澄清会话的 chat_history 为 [user1, assistant1, user2]
- **WHEN** ReAct Agent 调用 run_deep_analysis 工具实际启动管线
- **THEN** 系统 SHALL 将 pipeline_anchor 写为 3（最后一条 user 消息 user2 的索引 + 1）
- **AND** 当前轮 assistant 在途消息的增量 upsert 不影响锚点值

#### Scenario: 会话详情返回锚点

- **GIVEN** 某会话的 pipeline_anchor 已写入
- **WHEN** 前端请求 GET /api/sessions/{sessionId}
- **THEN** 响应 SHALL 包含 pipeline_anchor 整数值
- **AND** 未写入过的会话（旧数据）返回 NULL/缺失，前端走回退逻辑

