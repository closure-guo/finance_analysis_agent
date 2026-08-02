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
- **AND** 非 chat 类型的会话在第一个用户消息后插入报告消息（含 report_markdown、chart_data、stock_name、duration_ms）

#### Scenario: 会话时间格式化兜底

- **GIVEN** 会话的 created_at 字段缺失、非法或为 epoch 占位值（年份 <= 1970）
- **WHEN** 在侧边栏渲染会话时间
- **THEN** 显示"未知时间"而非 "Invalid Date"

### Requirement: SSE Stream Abort Control

系统 SHALL 使用 AbortController 管理前端 SSE 订阅连接的生命周期。AbortController 仅控制本地订阅的断开，SHALL NOT 作为终止后端生成任务的手段；终止生成 SHALL 通过显式取消操作调用 `POST /api/sessions/{id}/cancel`。切换会话、新建分析不再触发对生成任务的中断语义。

#### Scenario: 显式停止生成

- **GIVEN** 某会话的生成任务正在运行
- **WHEN** 用户点击"停止"按钮
- **THEN** 调用 POST /api/sessions/{id}/cancel 取消后台任务
- **AND** 收到 interrupted 终态事件后结束本地流式状态
- **AND** 半截回复保留展示并带中断标记

#### Scenario: 切换会话仅断开本地订阅

- **GIVEN** 深度分析或快速对话 SSE 流正在进行
- **WHEN** 用户选择另一个会话或新建分析
- **THEN** 调用本地 abort 断开当前订阅连接（AbortError 静默退出）
- **AND** SHALL NOT 调用后端取消端点
- **AND** 后台生成任务不受影响

#### Scenario: 删除当前会话时取消生成

- **GIVEN** SSE 流正在进行，用户删除当前活动会话
- **WHEN** 删除操作执行
- **THEN** 断开本地订阅连接
- **AND** 该会话的后台任务随会话删除而终止（后端删除会话时取消其活跃任务）
- **AND** 重置 currentSessionId 为 null、清空消息列表、appState 切换为 'empty'

#### Scenario: 每会话独立的订阅连接

- **GIVEN** 上一轮 SSE 订阅已断开或完成
- **WHEN** 发起新的 startAnalysis、quickChat 或恢复端点订阅
- **THEN** 在该会话的 streamRegistry 条目中创建新的 AbortController
- **AND** 不同会话的 AbortController 互不影响

#### Scenario: 非中断的连接错误显示错误消息

- **GIVEN** SSE 订阅连接进行中
- **WHEN** 发生非 AbortError 的连接错误
- **THEN** 深度模式下添加 error 类型消息显示"连接错误: {message}"
- **AND** 快速模式下将助手消息更新为 error 类型
- **AND** 错误消息注明可按 after_seq 重连恢复（若该会话任务仍在运行）

## ADDED Requirements

### Requirement: Session Running Indicator

系统 SHALL 在侧边栏为正在运行生成任务的会话展示"生成中"指示（如呼吸灯/旋转图标），任务结束（完成、中断、出错）后移除。指示状态 SHALL 由 session 的 status 与实时事件流共同驱动，切换页面视图不影响其准确性。

#### Scenario: 运行中的会话显示指示

- **GIVEN** 会话 A 的生成任务正在运行
- **WHEN** 渲染侧边栏会话列表
- **THEN** 会话 A 条目显示"生成中"指示，无论其是否为当前选中会话

#### Scenario: 任务结束后移除指示

- **GIVEN** 会话 A 显示"生成中"指示
- **WHEN** 收到 done / interrupted / error 终态事件，或会话快照 status 非 running
- **THEN** 移除该会话的"生成中"指示

#### Scenario: 运行中会话拒绝输入并提示

- **GIVEN** 当前选中会话正在运行生成任务
- **WHEN** 用户在输入框提交新消息
- **THEN** 展示"该会话正在生成中，可停止后再发"提示
- **AND** 不发送请求（后端 409 为兜底，前端应先拦截）
