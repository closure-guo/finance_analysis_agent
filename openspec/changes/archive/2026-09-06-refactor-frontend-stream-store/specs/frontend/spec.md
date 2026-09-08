## MODIFIED Requirements

### Requirement: Session Selection

系统 SHALL 在用户选择已有会话时加载该会话的完整历史并切换到报告视图。选择会话 SHALL NOT 中断该会话或其他会话的后台生成任务；若目标会话正在运行，前端 SHALL 经恢复端点重连其事件流，使输出内容继续增长。切出当前会话时仅断开本地订阅连接。

#### Scenario: 选择会话加载历史

- **GIVEN** 侧边栏会话列表中有一个会话
- **WHEN** 用户点击该会话
- **THEN** 断开当前会话的本地 SSE 订阅连接（不调用后端取消，不影响后台任务）
- **AND** 向 GET /api/sessions/{sessionId} 发起请求获取会话详情
- **AND** 非活跃会话的 messages 在切换时丢弃，切回时从后端重建
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


#### Scenario: 多轮澄清会话的报告插入位置

- **GIVEN** 非 chat 会话的 chat_history 为 [用户提问, 助手搜索思考, 用户确认股票]，且 pipeline_anchor 指向最后一条用户消息之后
- **WHEN** 构建消息列表
- **THEN** 消息顺序为：用户提问 → 助手思考/工具调用 → 用户确认 → 管线完成时间轴 → 报告消息
- **AND** 报告消息 SHALL NOT 出现在任何用户消息之前

#### Scenario: 报告后追问会话的报告插入位置

- **GIVEN** 非 chat 会话的 chat_history 为 [用户提问, 用户追问, 助手追问回复]，且 pipeline_anchor 指向第一条用户消息之后
- **WHEN** 构建消息列表
- **THEN** 消息顺序为：用户提问 → 管线完成时间轴 → 报告消息 → 用户追问 → 助手追问回复

### Requirement: New Analysis Reset

系统 SHALL 在用户点击"新建分析"时中断进行中的 SSE 流并完全重置应用状态。

#### Scenario: 新建分析重置状态

- **GIVEN** 应用处于任意状态（analyzing/report/clarifying）
- **WHEN** 用户点击侧边栏"新建分析"按钮
- **THEN** 中断进行中的 SSE 流
- **AND** 重置 currentSessionId 为 null
- **AND** 清空消息列表
- **AND** appState 切换为 'empty'

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
- **THEN** StreamStore 为该会话创建新的 AbortController
- **AND** 不同会话的 AbortController 互不影响

#### Scenario: 非中断的连接错误显示错误消息

- **GIVEN** SSE 订阅连接进行中
- **WHEN** 发生非 AbortError 的连接错误
- **THEN** 深度模式下添加 error 类型消息显示"连接错误: {message}"
- **AND** 快速模式下将助手消息更新为 error 类型
- **AND** 错误消息注明可按 after_seq 重连恢复（若该会话任务仍在运行）

### Requirement: Streaming State Defensive Cleanup

系统 SHALL 保证 SSE 流结束时（reader 正常结束或连接异常断开）助手消息的流式状态被清除，使流式游标不依赖单一终态事件。当 SSE 流结束但前端未收到终态事件（done/interrupted/error）时，前端 SHALL 将当前轮次的助手消息 `streaming` 置为 false。终态事件处理与防御性清理对 `streaming` 的设置 SHALL 幂等，重复设置无副作用。

#### Scenario: 流结束未收到终态事件时清除游标

- **GIVEN** 深度分析或快速对话 SSE 流进行中，助手消息 streaming=true
- **WHEN** SSE reader 正常结束（读到流末尾）但未收到 done/interrupted/error 终态事件
- **THEN** 前端 SHALL 将助手消息 streaming 置为 false
- **AND** 流式游标消失，用户可继续追问

#### Scenario: 连接异常断开时清除游标

- **GIVEN** 深度分析或快速对话 SSE 流进行中，助手消息 streaming=true
- **WHEN** 发生非 AbortError 的连接错误导致流中断
- **THEN** 前端 SHALL 将助手消息 streaming 置为 false
- **AND** 展示连接错误消息

#### Scenario: 终态事件与防御性清理幂等

- **GIVEN** SSE 流进行中，助手消息 streaming=true
- **WHEN** 先收到 done 终态事件（streaming 置 false），随后 reader 结束触发防御性清理
- **THEN** 防御性清理再次设置 streaming=false 无副作用
- **AND** 游标保持消失状态，不闪烁或复活

> **关于原 REMOVED 段（2026-09-06 rebase 说明）**：原 delta 声明移除「前端流状态快照层」「ref 镜像同步机制」「手写守卫函数族」三个需求，但经查（git -S 全历史）三者从未进入主规范库（属 Aug-5 时代未归档链路的产物），故无 REMOVED 操作可言。移除理由仍有存档价值：
>
> - **快照层**：后端事件日志（session_events 表 + stream?after_seq= 断点续传）就绪后，前端快照层冗余且双事实源互相打架；改为切换时丢弃非活跃会话 messages、切回时从后端重建。
> - **ref 镜像**：19 个 ref 镜像的存在理由（闭包防旧值/切换快照）被 StreamStore 单一事实源消除。
> - **手写守卫族**：saveCurrentStreamState / ensureSingleReader 等 7+ 守卫的功能由 store 内部机制（switchSession 原子协议、applyEvent seq 守门、pump 单读取器）替代，3 处手写 getReader() 循环收敛为 1 处 pump。
