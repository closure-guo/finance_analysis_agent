# Delta Spec: frontend

## MODIFIED Requirements

### Requirement: Clarification Conversation Flow

深度模式下，系统 SHALL 将意图澄清阶段的交互（search_stock、web_search、thinking）走对话消息流，不触发管线 UI。仅当 Agent 调用 run_deep_analysis 工具时才进入管线 UI。澄清阶段的思考/工具调用按时间序列写入对话流消息的 `agentTimeline`。

澄清/对话流事件（thinking_token、thinking_replace、thinking_to_answer、search_*、tool_call、chat_token）的路由 SHALL 按**事件自身归属**判定，而非「管线消息是否已创建」这一全局状态：`thinking_token` 仅当事件携带管线节点标识（`node` 字段）时才写入管线消息的节点时序，否则一律写入对话流消息的 `agentTimeline`——即使管线消息已存在（如多轮会话中上一轮已触发管线）。`thinking_replace` / `thinking_to_answer` 作用于对话流消息末尾 thinking item，SHALL 始终路由到对话流，SHALL NOT 因管线消息存在而被丢弃。

> 来源：ADR-0017 D1 - 深度模式入口统一走 ReAct Agent 对话流

#### Scenario: 澄清阶段走对话流

- **GIVEN** 深度分析 SSE 流进行中，尚未收到 run_deep_analysis tool_call
- **WHEN** 收到 search_stock / web_search / batch_web_search 的 tool_call 事件
- **THEN** 工具调用作为 `{type:'tool_call', ...}` TimelineItem 追加到对话流消息的 `agentTimeline`，不创建管线消息
- **AND** appState 保持 'clarifying'

#### Scenario: 思考过程在澄清阶段走对话流

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（未进入管线模式）
- **WHEN** 收到 thinking_token / thinking_replace / thinking_to_answer 事件
- **THEN** 思考 token 追加到对话流消息 `agentTimeline` 末尾的 thinking item（若末尾非 thinking item 则新建），不写入管线消息

#### Scenario: 管线消息存在时不携带 node 的思考仍走对话流

- **GIVEN** 深度分析 SSE 流进行中，管线消息已创建（pipelineMsgRef 非空，如多轮会话上一轮已触发管线，或本轮 run_deep_analysis 已发出后 Agent 继续澄清）
- **WHEN** 收到不携带 `node` 字段的 thinking_token 事件
- **THEN** 该思考 token SHALL 写入当前对话流消息的 `agentTimeline`，SHALL NOT 写入管线消息的节点时序
- **AND** 对话流消息的思考横幅正常显示，不错位到管线卡片

#### Scenario: 管线节点思考按 node 归属进管线 UI

- **GIVEN** 管线运行中（pipelineMsgRef 非空）
- **WHEN** 收到携带 `node` 字段的 thinking_token 事件（管线节点的思考）
- **THEN** 该 token SHALL 写入管线消息对应节点的时序（nodeTimelines[node]）
- **AND** 不写入对话流消息

#### Scenario: thinking_replace / thinking_to_answer 不被管线状态丢弃

- **GIVEN** 深度分析 SSE 流进行中，管线消息已创建（pipelineMsgRef 非空）
- **WHEN** 收到 thinking_replace 事件（DSML 清理）或 thinking_to_answer 事件
- **THEN** 事件 SHALL 路由到对话流处理（替换/切割对话流消息末尾 thinking item）
- **AND** SHALL NOT 被静默丢弃
- **AND** DSML 清理后对话流思考横幅不残留原始 DSML 文本或回复前缀

#### Scenario: run_deep_analysis 触发管线 UI

- **GIVEN** 深度分析 SSE 流进行中
- **WHEN** 收到 tool_call 事件且 name 为 'run_deep_analysis'
- **THEN** 创建管线消息（pipelineMsg），内容为"开始深度分析..."
- **AND** appState 切换为 'analyzing'
- **AND** 后续的 parsing/resolved/node_start/node_complete/report_chunk/report_ready 事件写入管线消息

#### Scenario: awaiting_input 切换到澄清等待

- **GIVEN** 深度分析 SSE 流进行中
- **WHEN** 收到 awaiting_input 事件
- **THEN** appState 切换为 'clarifying'
- **AND** 助手消息停止流式状态（streaming = false）

#### Scenario: 管线完成后 pipelineMsgRef 收口

- **GIVEN** 管线消息已创建，深度分析管线运行中
- **WHEN** 收到 report_ready 事件（管线完成）或 done 终态事件
- **THEN** 前端 SHALL 将 pipelineMsgRef 置 null
- **AND** 后续轮次的澄清思考不再被路由到已完成的管线消息
