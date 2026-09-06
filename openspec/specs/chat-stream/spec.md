# Chat Stream Specification

## Purpose

定义 AG-UI 协议 quick 模式对话通道（POST /api/agui/quick）的事件流契约与 assistant-ui 渲染语义。
## Requirements
### Requirement: AG-UI 协议端点

系统 SHALL 提供 `POST /api/agui/quick` 端点：接受 AG-UI `RunAgentInput`，以 SSE 返回标准 AG-UI 事件流（至少包含 `RUN_STARTED`、`TEXT_MESSAGE_START`、`TEXT_MESSAGE_CONTENT`、`TEXT_MESSAGE_END`、`RUN_FINISHED`/`RUN_ERROR`）。事件 SHALL 符合 AG-UI 协议的类型定义；每个 run SHALL 以且仅以一个终止事件（`RUN_FINISHED` 或 `RUN_ERROR`）结束。对话内容 SHALL 沿用现有 session_store 持久化，落库结果与事件流内容一致。

#### Scenario: 正常对话事件序列

- **GIVEN** 用户在 quick 模式发送一条问题
- **WHEN** 客户端消费 `POST /api/agui/quick` 的 SSE 流
- **THEN** 事件序列为 `RUN_STARTED` → ≥1 组 `TEXT_MESSAGE_START/CONTENT/END` → `RUN_FINISHED`
- **AND** `TEXT_MESSAGE_CONTENT` 分块按顺序拼接后与落库的 assistant 回复全文一致

#### Scenario: LLM 异常以 RUN_ERROR 终止

- **GIVEN** LLM 调用失败（如 API Key 无效）
- **WHEN** run 执行中断
- **THEN** 流以 `RUN_ERROR` 事件终止（含错误信息），不悬挂不输出半截 `RUN_FINISHED`
- **AND** 该次对话不落库为成功回复

#### Scenario: 管线通道零影响

- **GIVEN** AG-UI 端点已上线
- **WHEN** 深度模式分析运行并消费现有 `/api/stream` 事件流
- **THEN** 事件序列与 AG-UI 端点上线前完全一致（既有事件契约测试无修改通过）

### Requirement: assistant-ui 渲染 quick 模式对话

quick 模式消息流 SHALL 使用 assistant-ui Thread 组件渲染：流式增量逐块呈现、回复结束后无残留流式指示器、历史消息从 session_store 快照恢复。视觉 SHALL 使用设计令牌（refactor-ui-design-system）与现有 `components/ui/` 原语，无硬编码色值。

#### Scenario: 流式渲染生命周期

- **WHEN** 用户发送问题并等待回复
- **THEN** assistant 消息以流式增量呈现，`RUN_FINISHED` 后流式指示器消失
- **AND** 渲染出的最终文本与 session_store 落库内容一致

#### Scenario: 历史恢复渲染

- **GIVEN** 某 quick 会话已有历史对话
- **WHEN** 用户刷新页面后选回该会话（或从其它会话切回）
- **THEN** assistant-ui Thread 完整渲染历史消息（含本次 AG-UI 通道之前的旧消息），顺序与落库一致

### Requirement: 会话切换守卫语义不回退

AG-UI 通道 SHALL 满足与现有通道等价的切换守卫：用户在流式进行中切换会话时，旧 run 的事件 SHALL NOT 渲染进新会话的消息区；切回时以 session_store 快照渲染（允许显示进行中标记），不产生重复或错位消息。

#### Scenario: 流式中切换会话无串流

- **GIVEN** quick 模式对话流式输出进行中
- **WHEN** 用户切换到另一会话再切回
- **THEN** 消息区不出现另一会话的内容
- **AND** 切回后以快照渲染，不重复追加同一条回复

### Requirement: 双轨隔离

AG-UI 通道 SHALL 仅承载 quick 模式对话；深度模式分析、管线时间线事件 SHALL NOT 经由 AG-UI 端点传输。两通道 SHALL 可独立部署回退（移除 AG-UI 路由后深度模式完整可用）。

#### Scenario: 回退隔离

- **WHEN** 移除/停用 `/api/agui/quick` 路由
- **THEN** 深度模式分析与管线时间线功能不受任何影响
- **AND** quick 模式历史会话仍可查看（仅新对话流暂不可用）

### Requirement: 流式事件真实性（禁系统冒充）

LLM 事件通道（thinking_token / tool_call / tool_result）SHALL 仅承载模型真实推理与真实工具调用：系统 SHALL NOT 生成伪造的 thinking_token（如预搜索说明、节点执行/完成文案）、伪造的 tool_call，SHALL NOT 在用户消息中预注入搜索结果替代模型自主决策。时效性查询的搜索 SHALL 由模型基于 reasoning 自行决定并发起。管线节点进度 SHALL 经管线事件（node_start / node_complete / 节点时序）呈现，SHALL NOT 经 thinking_token 旁路下发。

#### Scenario: 时效性查询由模型自主搜索

- GIVEN 深度/快速通道收到不含股票代码、含时效性关键词的查询
- WHEN 流式输出
- THEN 系统 SHALL NOT 发出预生成的 thinking_token / tool_call / search_start（预搜索旁路）
- AND 模型若判定需要搜索，SHALL 经 ReAct 工具调用真实发起 web_search（真实思考 + 真实工具事件）

#### Scenario: 管线进度不经思考旁路

- GIVEN 深度分析管线运行中
- WHEN 节点开始或完成
- THEN 系统 SHALL NOT 生成 `▶ …` / `✓ …` 形式的 thinking_token
- AND 节点进度 SHALL 由 node_start / node_complete 及管线时间轴承载

#### Scenario: 节点真实思考不受影响

- GIVEN 深度分析管线运行中
- WHEN 节点 LLM 产生真实 thinking 输出
- THEN 该 thinking SHALL 照常经 thinking_token 转发（custom mode 转发路径保留）

