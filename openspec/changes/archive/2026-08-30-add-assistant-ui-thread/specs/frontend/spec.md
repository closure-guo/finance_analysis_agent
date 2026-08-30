# frontend delta: add-assistant-ui-thread

## MODIFIED Requirements

### Requirement: Quick Chat Entry

系统 SHALL 通过 POST /api/agui/quick（AG-UI 协议）发起快速对话：请求体为 AG-UI RunAgentInput 形态（messages 含 user 消息、threadId；新增会话时 threadId 为空，服务端新建会话并经 RUN_STARTED.threadId 回传绑定）；api_key 与 llm_config 经 forwardedProps 透传。后续发送 SHALL 携带由 RUN_STARTED 回传的会话 id 作为 threadId，且追问 SHALL 挂载于当前对话末尾（RunAgentInput 携带完整历史上下文）。

quick 模式消息流的渲染实现 SHALL 使用 assistant-ui Thread + AG-UI runtime：流式增量逐块呈现、RUN_FINISHED 后无残留流式指示器、思考段与工具调用以消息 parts 按时间顺序呈现；历史消息恢复 SHALL 沿用 MessageItem 快照渲染路径（rebuildSession），Thread 只接管本 mount 发起的新 run。发送入口、回复完成态、会话切换守卫行为 SHALL 与替换前一致；深度模式相关测试零修改通过。
(Previously: 系统 SHALL 通过 POST /api/chat 发起快速对话，请求体包含 message、user_id、api_key，以及可选的 session_id。)

#### Scenario: 从空状态发起快速对话

- **GIVEN** 空状态首页，模式为 'quick'，API Key 已配置
- **WHEN** 用户输入文本并发送
- **THEN** 向 POST /api/agui/quick 发起请求，body 为 RunAgentInput 形态且 threadId 为空
- **AND** appState 从 'empty' 切换到 'clarifying'
- **AND** 用户消息与助手回复经 assistant-ui Thread 渲染，RUN_STARTED.threadId 回传后绑定新会话

#### Scenario: 对话中后续发送

- **GIVEN** 会话视图，已有 currentSessionId
- **WHEN** 用户在底部输入栏输入文本并发送
- **THEN** 向 POST /api/agui/quick 发起请求，threadId 为当前会话 id
- **AND** 追问挂载于当前对话末尾，第二轮回复为独立消息（不串入第一轮）

#### Scenario: 刷新恢复渲染历史

- **GIVEN** 某 quick 会话已有历史对话
- **WHEN** 用户刷新页面后自动恢复该会话
- **THEN** 历史消息由 MessageItem 快照路径渲染（含思考/工具横幅时序），顺序与落库一致
- **AND** assistant-ui Thread 重挂载后为空壳，不重复渲染历史

### Requirement: Quick Chat Search Events

quick 模式下搜索类工具（web_search 等）SHALL 经 AG-UI `TOOL_CALL_START`/`TOOL_CALL_ARGS`/`TOOL_CALL_END`/`TOOL_CALL_RESULT` 事件流承载，并渲染为工具调用横幅（「调用工具 · {工具名}」单行横幅），按事件时间顺序与思考段交错呈现；历史快照恢复时以 `tool_call` 类型 TimelineItem 渲染工具调用横幅（label 按工具名映射）。独立搜索横幅（SearchBanner）语义 SHALL 保留给深度模式管线/澄清流。
(Previously: 系统 SHALL 在快速模式下处理搜索类 SSE 事件（search_start/search_result/search_error），生成 `search` 类型 TimelineItem，渲染为独立的可折叠搜索横幅（SearchBanner）。)

#### Scenario: 搜索工具调用实时呈现

- **GIVEN** quick 模式对话流式输出进行中，Agent 调用 web_search
- **WHEN** 收到 TOOL_CALL_* 事件族（以 TOOL_CALL_END 闭合）
- **THEN** assistant 消息内按时间顺序渲染「调用工具 · web_search」横幅
- **AND** 工具调用处于 active 态时 run 终止事件 SHALL NOT 被客户端校验拒绝

#### Scenario: 刷新恢复含工具调用时序

- **GIVEN** 某 quick 会话历史中含带工具调用的回复（agentTimeline 结构化落库）
- **WHEN** 用户刷新页面恢复该会话
- **THEN** 历史快照按落库 agentTimeline 渲染思考/工具横幅时序
- **AND** 搜索类工具步骤 SHALL NOT 被恢复路径丢弃
