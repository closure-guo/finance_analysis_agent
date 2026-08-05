# Frontend Delta: fix-history-report-anchor

## MODIFIED Requirements

### Requirement: Session Selection

系统 SHALL 在用户选择已有会话时加载该会话的完整历史并切换到报告视图。选择会话 SHALL NOT 中断该会话或其他会话的后台生成任务；若目标会话正在运行，前端 SHALL 经恢复端点重连其事件流，使输出内容继续增长。切出当前会话时仅断开本地订阅连接，保留按 sessionId 累积的流状态以便切回时快速恢复。

#### Scenario: 选择会话加载历史

- **GIVEN** 侧边栏会话列表中有一个会话
- **WHEN** 用户点击该会话
- **THEN** 断开当前会话的本地 SSE 订阅连接（不调用后端取消，不影响后台任务）
- **AND** 向 GET /api/sessions/{sessionId} 发起请求获取会话详情
- **AND** 保留 streamRegistry 中按 sessionId 累积的流状态，仅重置当前视图的消息列表
- **AND** 设置 currentSessionId 并将 appState 切换为 'report'
- **AND** 按 session_type 锁定模式

#### Scenario: 切换会话不中断生成

- **GIVEN** 会话 A 的深度分析或快速对话正在流式输出
- **WHEN** 用户点击切换到会话 B
- **THEN** 会话 A 的后台生成任务继续运行
- **AND** 侧边栏会话 A 保持"生成中"指示
- **AND** 不向会话 A 发送任何取消/中断请求

#### Scenario: 切回运行中的会话并续传

- **GIVEN** 用户从正在流式输出的会话 A 切出，期间任务继续产出事件
- **WHEN** 用户再次点击会话 A
- **THEN** 加载会话快照后，经 GET /api/sessions/A/stream（携带最后已消费的 seq）重连事件流
- **AND** 重放事件与实时事件经同一处理函数消费，UI 幂等重建
- **AND** 输出内容从切出时的位置继续增长，不重复、不遗漏

#### Scenario: 切回已中断的会话

- **GIVEN** 会话 A 的生成被显式取消或服务重启导致中断
- **WHEN** 用户点击会话 A
- **THEN** 展示已落库的半截回复及"输出已中断，可追问继续"标记
- **AND** 不显示无限转圈的 streaming 状态

#### Scenario: 恢复会话对话历史

- **GIVEN** 加载的会话详情包含 chat_history
- **WHEN** 构建消息列表
- **THEN** 按 chat_history 顺序重建消息：role='user' 的条目渲染为用户消息，其余渲染为助手消息
- **AND** 助手消息包含 thinking 内容和 tool_calls 记录（若历史中存在）
- **AND** 非 chat 类型的会话在管线触发锚点（pipeline_anchor，即 chat_history 第 N 条之后）插入报告消息（含 report_markdown、chart_data、stock_name、duration_ms）与管线完成时间轴
- **AND** pipeline_anchor 缺失（旧会话）时回退为在第一个用户消息后插入报告消息

#### Scenario: 多轮澄清会话的报告插入位置

- **GIVEN** 非 chat 会话的 chat_history 为 [用户提问, 助手搜索思考, 用户确认股票]，且 pipeline_anchor 指向最后一条用户消息之后
- **WHEN** 构建消息列表
- **THEN** 消息顺序为：用户提问 → 助手思考/工具调用 → 用户确认 → 管线完成时间轴 → 报告消息
- **AND** 报告消息 SHALL NOT 出现在任何用户消息之前

#### Scenario: 报告后追问会话的报告插入位置

- **GIVEN** 非 chat 会话的 chat_history 为 [用户提问, 用户追问, 助手追问回复]，且 pipeline_anchor 指向第一条用户消息之后
- **WHEN** 构建消息列表
- **THEN** 消息顺序为：用户提问 → 管线完成时间轴 → 报告消息 → 用户追问 → 助手追问回复

#### Scenario: 会话时间格式化兜底

- **GIVEN** 会话的 created_at 字段缺失、非法或为 epoch 占位值（年份 <= 1970）
- **WHEN** 在侧边栏渲染会话时间
- **THEN** 显示"未知时间"而非 "Invalid Date"
