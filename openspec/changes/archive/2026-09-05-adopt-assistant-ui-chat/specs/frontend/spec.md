# frontend delta: adopt-assistant-ui-chat

## ADDED Requirements

### Requirement: 消息流由 assistant-ui 渲染

聊天消息区 SHALL 使用 assistant-ui Thread 组件渲染：token 级流式输出、生成中自动跟随滚动（用户上翻时暂停跟随）、中断后保留已生成内容。

#### Scenario: 流式渲染与滚动跟随

- **GIVEN** 一次分析请求正在流式返回
- **WHEN** token 持续到达
- **THEN** 正文 SHALL 渐进渲染且视图自动跟随最新内容
- **AND** 用户主动上翻后 SHALL 暂停跟随，回到底部后恢复

#### Scenario: 中断保留已生成内容

- **WHEN** 用户在生成中点击停止
- **THEN** 已生成内容 SHALL 完整保留，不消失、不回退

### Requirement: SSE 事件适配层

前端 SHALL 提供单一 adapter 翻译层，将后端全部 SSE 事件类型映射为 assistant-ui 消息部件；每类事件 SHALL 有对应单测；未知事件类型 SHALL 安全忽略且不崩溃。

#### Scenario: 事件类型全覆盖

- **GIVEN** 后端 SSE 事件类型枚举（chat_token、thinking、工具调用、管线节点、report_ready 等）
- **WHEN** 检查 adapter 实现与单测
- **THEN** 每个事件类型 SHALL 存在映射逻辑与对应测试

#### Scenario: 未知事件安全忽略

- **WHEN** adapter 收到未定义的事件类型
- **THEN** 前端 SHALL 忽略该事件并继续处理后续事件，不抛错、不中断流

### Requirement: 思考过程折叠卡片

思考内容 SHALL 渲染为可折叠卡片：流式中显示进行态（如"思考中…"），完成后默认收起、可展开查看完整推理内容。

#### Scenario: 思考卡流式与收起

- **GIVEN** 模型输出含 thinking 流
- **WHEN** 流式进行中
- **THEN** 显示思考卡片进行态
- **AND** 流结束后卡片默认收起，点击展开完整内容

### Requirement: 工具调用卡片

工具调用 SHALL 渲染为卡片：调用中显示 loading 态，完成后可展开查看参数与结果；澄清阶段的工具执行中 SHALL 沿用运行中拦截语义（禁止发送）。

#### Scenario: 工具调用状态展示

- **WHEN** agent 调用工具（如股票识别）
- **THEN** 卡片 SHALL 先显示 loading 态，完成后显示结果摘要
- **AND** 调用期间发送消息 SHALL 被拦截并提示

### Requirement: 输入区 Composer

输入区 SHALL 使用 assistant-ui Composer：Enter 发送、Shift+Enter 换行、输入为空时发送键禁用、会话运行中发送键变为停止按钮。

#### Scenario: 发送与停止切换

- **WHEN** 会话进入运行中
- **THEN** 发送按钮 SHALL 切换为停止按钮
- **AND** 点击停止 SHALL 中断当前流

### Requirement: 消息操作与独有部件

assistant 消息 hover SHALL 显示复制与重新生成操作；管线进度时间线、ECharts 图表、报告导出入口 SHALL 以自定义消息部件挂载，能力与现状一致。

#### Scenario: 独有部件能力不丢

- **WHEN** 深度分析完成
- **THEN** 消息区 SHALL 正常渲染管线时间线、报告图表与导出按钮
- **AND** 导出交互与 add-download-center 之前的既有行为一致

## MODIFIED Requirements

### Requirement: 会话运行中（含工具执行中）禁止发送

会话处于运行中（含澄清阶段工具执行中）时，前端 SHALL 拦截发送并提示；追问路径（后端不重发 `session_created`）下拦截同样生效。拦截主层 SHALL 迁移至 assistant-ui runtime 状态判定（运行中发送入口切换为停止按钮、提交通道关闭），App 层守卫（`isSessionRunning` / quick run 单飞守卫）保留为兜底。
(Previously: 拦截主层为 App 层 `isSessionRunning` 守卫 + streamStore 单读取器登记。)

#### Scenario: 澄清工具执行中发送被拦截

- **GIVEN** 某会话澄清阶段 agent 正在执行工具（SSE 流存活）
- **WHEN** 用户在该会话输入框发送消息
- **THEN** 前端 SHALL 判定 `isSessionRunning(sessionId)` 为 true
- **AND** 运行中发送入口切换为停止按钮（提交通道关闭），App 层守卫命中时显示「该会话正在生成中」toast
- **AND** 不发出新的分析/对话请求

#### Scenario: 追问路径登记 abort 使拦截生效

- **GIVEN** 一次追问（已有 sessionId，后端不重发 `session_created`）
- **WHEN** 前端发起 SSE 请求并创建 `AbortController`
- **THEN** 前端 SHALL 在 fetch 发出前将其登记为该会话的活跃读取器（单读取器保证）
- **AND** 运行状态判定据此生效

#### Scenario: 运行中拦截（验收基准不变）

- **GIVEN** 某会话正在生成（含工具执行中）
- **WHEN** 用户发送消息
- **THEN** 前端 SHALL 拦截发送并显示顶部 toast 提示

