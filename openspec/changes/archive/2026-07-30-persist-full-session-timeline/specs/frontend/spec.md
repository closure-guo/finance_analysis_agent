# Delta Spec: frontend（persist-full-session-timeline）

## MODIFIED Requirements

### Requirement: Chat History Restore With Tool Calls

系统 SHALL 在加载已有会话时恢复助手消息的 `agentTimeline`：**优先**使用 `chat_history` 条目中持久化的 `agentTimeline` 字段（结构化 TimelineItem 数组，含思考/搜索/工具调用的真实交错时序）原样重建；仅当该字段缺失（旧会话）时回退 `buildTimelineFromHistory` 的「思考在前、工具调用在后」近似恢复。

#### Scenario: 优先用持久化 agentTimeline 原样恢复

- **GIVEN** 加载的会话 `chat_history` 中某条助手消息包含 `agentTimeline` 字段
- **WHEN** 构建助手消息
- **THEN** 系统 SHALL 将 `agentTimeline` 反序列化后直接作为消息的 agentTimeline（保留 thinking/search/tool_call 的真实交错顺序）
- **AND** 搜索记录（type='search'）按其真实时序位置恢复为搜索横幅
- **AND** SHALL NOT 再走"思考在前、工具调用在后"的拍平近似

#### Scenario: 旧数据回退近似恢复

- **GIVEN** 加载的会话 `chat_history` 中某条助手消息仅有 `thinking`/`tool_calls`，无 `agentTimeline`
- **WHEN** 构建助手消息
- **THEN** 系统 SHALL 回退 buildTimelineFromHistory：从 thinking（合并字符串）构建 thinking item、从 tool_calls 按序构建 tool_call items
- **AND** 恢复过程不报错、消息正常显示

## ADDED Requirements

### Requirement: 管线时序恢复

系统 SHALL 在加载已有会话时，从会话详情的 `pipeline_timelines`（JSON：`{node: [TimelineItem]}`）恢复深度分析管线消息的 `nodeTimelines`，使各节点的思考/工具调用记录切换会话后完整可见。

#### Scenario: 切回会话恢复管线节点时序

- **GIVEN** 某深度分析会话的 pipeline_timelines 已持久化（含各节点思考/工具时序）
- **WHEN** 用户切换到该会话（运行中或已完成）
- **THEN** 前端 SHALL 反序列化 pipeline_timelines 为管线消息的 nodeTimelines
- **AND** 各节点的思考内容、网络搜索、工具调用记录按原时序展示
- **AND** 非法/缺失的 pipeline_timelines 回退为空（时间轴树仍由 pipeline_snapshot 恢复）
