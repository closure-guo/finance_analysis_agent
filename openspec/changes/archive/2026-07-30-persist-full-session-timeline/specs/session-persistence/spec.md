# Delta Spec: session-persistence（persist-full-session-timeline）

## ADDED Requirements

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
