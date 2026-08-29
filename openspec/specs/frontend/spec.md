# Frontend Specification

> 来源：incident 010（缺少行为 spec 约束）、ADR-0012（session 流式与自然输入）、ADR-0017（意图澄清对话流）
> 基线构建日期：2026-07-24
> 说明：本 spec 从 `frontend/src/App.tsx`、`frontend/src/types.ts` 现有实现反推，捕获当前行为作为真相来源。

## Purpose

定义 React 前端（React 18 + Vite + TailwindCSS）的用户交互行为契约。覆盖空状态首页、API Key 管理、会话管理、深度/快速两种模式的 SSE 流式渲染、管线进度展示、报告渲染与文件下载。
## Requirements

> 以下是前端 35 个行为契约，按 6 个行为域分组。每组覆盖一个独立的交互主题，可独立审阅。

| 行为域 | 需求数 | 通俗说明 |
|--------|--------|----------|
| A. 首页与输入 | 5 | 用户第一次打开页面看到什么、怎么选模式、怎么配 API Key |
| B. 会话管理 | 7 | 左侧栏的会话列表：搜索、切换、删除、重命名、新建 |
| C. 深度分析流 | 11 | 深度模式的核心：从发起到报告生成，SSE 事件如何驱动 UI 变化 |
| D. 快速对话流 | 2 | 快速模式的入口和搜索结果展示 |
| E. 对话流公共机制 | 3 | 两种模式共用的思考/工具/错误处理和 SSE 中断逻辑 |
| F. 渲染与展示 | 7 | 报告卡片、思考横幅、工具调用横幅等 UI 组件的渲染规则 |

---

<!-- A. 首页与输入：用户第一次打开页面看到什么、怎么选模式、怎么配 API Key -->

### Requirement: Empty State Landing Page

当无活动会话时，系统 SHALL 显示空状态首页，包含品牌标识、模式选择器、文本输入框和 API Key 状态指示。

#### Scenario: 首次进入显示空状态

- **GIVEN** 应用刚加载且无 currentSessionId
- **WHEN** 页面渲染
- **THEN** 显示 logo、标题"Finance Analysis Agent"、副标题"AI 驱动的 A 股投研分析系统"
- **AND** 显示模式选择器（默认选中"深度研究"）
- **AND** 显示文本输入框，placeholder 随模式变化
- **AND** 显示 4 个特性卡片（4 维并行分析、Bull/Bear 辩论、Risk 压力测试、结构化报告）

#### Scenario: 空状态下输入并发送

- **GIVEN** 空状态首页，API Key 已配置
- **WHEN** 用户在输入框输入文本并按 Enter（非 Shift+Enter）
- **THEN** 系统根据当前模式调用对应流程（深度 -> startAnalysis，快速 -> quickChat）
- **AND** 输入框清空
- **AND** 应用状态从 'empty' 切换到 'clarifying'

#### Scenario: 空状态下未配置 API Key 时发送

- **GIVEN** 空状态首页，API Key 未配置
- **WHEN** 用户输入文本并按 Enter
- **THEN** 不发起请求
- **AND** 弹出 API Key 配置弹窗

### Requirement: Mode Selection

系统 SHALL 提供两种分析模式：深度研究（deep）和快速模式（quick），模式决定后续的请求端点和交互流程。

#### Scenario: 空状态下切换模式

- **GIVEN** 空状态首页
- **WHEN** 用户点击模式下拉选择器并选择"快速模式"或"深度研究"
- **THEN** 当前模式更新为所选模式
- **AND** 输入框 placeholder 更新为对应模式的提示文案

#### Scenario: 快速模式 placeholder

- **GIVEN** 模式为 'quick'
- **THEN** 输入框 placeholder 为"输入问题，如：茅台、宁德时代怎么样"

#### Scenario: 深度模式 placeholder

- **GIVEN** 模式为 'deep'
- **THEN** 输入框 placeholder 为"输入股票名称或代码，如 茅台、300750"

### Requirement: Mode Locking After Session Creation

系统 SHALL 在会话创建后锁定模式切换，防止用户在已有会话中切换模式导致行为不一致。

#### Scenario: 会话存在时模式锁定

- **GIVEN** currentSessionId 不为 null
- **WHEN** 渲染底部输入栏（ChatInputBar）
- **THEN** 深度/快速模式切换按钮处于禁用状态
- **AND** 显示锁定图标提示"会话模式已锁定"

#### Scenario: 加载已有会话时按类型设置模式

- **GIVEN** 用户选择一个已有会话
- **WHEN** 会话详情加载完成
- **THEN** 若 session_type 为 'chat'，模式锁定为 'quick'
- **AND** 若 session_type 不为 'chat'（analysis），模式锁定为 'deep'

#### Scenario: 新建分析时解锁模式

- **GIVEN** 用户点击"新建分析"
- **WHEN** 应用状态重置为 'empty'
- **THEN** currentSessionId 为 null，模式切换按钮恢复可用

### Requirement: Dropdown Outside-Click Dismissal

系统 SHALL 在「模式切换」与「LLM 切换」下拉框展开后，支持点击下拉框以外的页面区域将其关闭，且同一输入栏内的两个下拉框互斥展开（打开一个时自动关闭另一个）。

#### Scenario: 空状态首页模式下拉框点击外部关闭

- **GIVEN** 空状态首页，模式切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** 模式切换下拉框关闭
- **AND** 当前模式不变，不触发任何输入发送动作

#### Scenario: 会话底部输入栏模式下拉框点击外部关闭

- **GIVEN** 会话视图，底部输入栏的模式切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** 模式切换下拉框关闭
- **AND** 当前模式与会话不变，不触发新会话

#### Scenario: 空状态首页 LLM 切换下拉框点击外部关闭

- **GIVEN** 空状态首页，已配置至少一个 LLM profile，LLM 切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** LLM 切换下拉框关闭
- **AND** 当前 LLM profile 不切换

#### Scenario: 会话底部输入栏 LLM 切换下拉框点击外部关闭

- **GIVEN** 会话视图，已配置至少一个 LLM profile，底部输入栏的 LLM 切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** LLM 切换下拉框关闭
- **AND** 当前 LLM profile 不切换

#### Scenario: 同一输入栏两个下拉框互斥展开

- **GIVEN** 空状态首页，模式切换下拉框已展开
- **WHEN** 用户点击同一输入栏内的 LLM 切换触发按钮
- **THEN** 模式切换下拉框关闭，LLM 切换下拉框展开
- **AND** 反向操作同样生效：LLM 切换下拉框展开时点击模式切换触发按钮，LLM 切换下拉框关闭、模式切换下拉框展开

#### Scenario: 再次点击触发按钮收起

- **GIVEN** 模式切换或 LLM 切换下拉框已展开
- **WHEN** 用户再次点击同一触发按钮
- **THEN** 下拉框关闭

#### Scenario: 点击选项执行动作并关闭

- **GIVEN** 模式切换或 LLM 切换下拉框已展开
- **WHEN** 用户点击下拉框内的某个选项
- **THEN** 执行该选项对应动作（切换模式 / 切换 LLM profile）
- **AND** 下拉框关闭
- **AND** 模式选项的 capability 门禁（`canEnterMode`）逻辑保持现状：门禁不允许的模式选项仍禁用且点击不生效

### Requirement: API Key Management

系统 SHALL 通过浏览器 localStorage 管理 DeepSeek API Key，未配置 Key 时阻止发送请求。

#### Scenario: 持久化 API Key

- **GIVEN** 用户在配置弹窗中输入 API Key 并点击确认
- **WHEN** 确认按钮被点击
- **THEN** API Key 保存到 localStorage（key: 'fa_api_key'）
- **AND** 关闭配置弹窗
- **AND** 空状态首页更新为"API Key 已配置"

#### Scenario: 清空 API Key

- **GIVEN** 用户在配置弹窗中清空输入框并点击确认
- **WHEN** 确认按钮被点击
- **THEN** localStorage 中的 'fa_api_key' 被移除
- **AND** 关闭配置弹窗

#### Scenario: 弹窗遮罩关闭

- **GIVEN** API Key 配置弹窗已打开
- **WHEN** 用户点击弹窗外部遮罩区域
- **THEN** 弹窗关闭，不保存当前输入

#### Scenario: 页面加载时恢复 API Key

- **GIVEN** 页面刷新或重新加载
- **WHEN** 应用初始化
- **THEN** 从 localStorage 读取 API Key 并恢复到应用状态

### Requirement: User Identity Persistence

系统 SHALL 在浏览器 localStorage 中持久化匿名用户 ID，用于标识发起请求的用户。

#### Scenario: 首次访问生成用户 ID

- **GIVEN** localStorage 中不存在 'fa_user_id'
- **WHEN** 应用初始化
- **THEN** 生成格式为 `user-{uuid}` 的唯一 ID 并保存到 localStorage

#### Scenario: 后续访问复用用户 ID

- **GIVEN** localStorage 中已存在 'fa_user_id'
- **WHEN** 应用初始化
- **THEN** 复用已存的用户 ID

---

<!-- B. 会话管理：左侧栏的会话列表：搜索、切换、删除、重命名、新建 -->

### Requirement: Session List Loading

系统 SHALL 在应用初始化时从后端加载会话历史列表并显示在侧边栏中。

#### Scenario: 初始化加载会话列表

- **GIVEN** 应用刚加载
- **WHEN** 应用初始化
- **THEN** 向 GET /api/sessions 发起请求
- **AND** 将返回的 sessions 数组填充到侧边栏列表

#### Scenario: 会话列表为空

- **GIVEN** 后端返回空会话列表
- **WHEN** 侧边栏渲染
- **THEN** 显示"暂无历史会话"提示

### Requirement: Session Search

系统 SHALL 支持在侧边栏按股票名称、股票代码或显示名称搜索会话。

#### Scenario: 输入搜索关键词过滤会话

- **GIVEN** 侧边栏已加载会话列表
- **WHEN** 用户在搜索框输入关键词
- **THEN** 会话列表实时过滤，匹配 stock_name、stock_code 或 display_name（大小写不敏感）的会话保留显示

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

### Requirement: Session Deletion

系统 SHALL 支持删除会话，删除当前活动会话时重置到空状态。

#### Scenario: 删除非当前会话

- **GIVEN** 侧边栏会话列表中有多个会话，用户删除非当前会话
- **WHEN** 用户点击删除按钮
- **THEN** 向 DELETE /api/sessions/{sessionId} 发起请求
- **AND** 从侧边栏列表中移除该会话

#### Scenario: 删除当前活动会话

- **GIVEN** 用户删除当前 currentSessionId 对应的会话
- **WHEN** 删除请求完成
- **THEN** 中断进行中的 SSE 流
- **AND** 重置 currentSessionId 为 null、清空消息列表、appState 切换为 'empty'

### Requirement: Session Renaming

系统 SHALL 支持通过双击会话显示名称进行内联重命名。

#### Scenario: 双击进入重命名编辑

- **GIVEN** 侧边栏会话列表中有一个会话
- **WHEN** 用户双击会话的 display_name
- **THEN** display_name 区域变为文本输入框，预填当前名称并自动聚焦

#### Scenario: 确认重命名

- **GIVEN** 重命名输入框已激活
- **WHEN** 用户按 Enter 或输入框失焦，且输入内容非空
- **THEN** 向 PATCH /api/sessions/{sessionId} 发起请求（body: { display_name }）
- **AND** 更新侧边栏列表中对应会话的 display_name

#### Scenario: 取消重命名

- **GIVEN** 重命名输入框已激活
- **WHEN** 用户按 Escape
- **THEN** 退出编辑模式，不发起请求，display_name 保持原值

### Requirement: New Analysis Reset

系统 SHALL 在用户点击"新建分析"时中断进行中的 SSE 流并完全重置应用状态。

#### Scenario: 新建分析重置状态

- **GIVEN** 应用处于任意状态（analyzing/report/clarifying）
- **WHEN** 用户点击侧边栏"新建分析"按钮
- **THEN** 中断进行中的 SSE 流
- **AND** 重置 currentSessionId 为 null、清空 streamingReportRef 和 pipelineMsgRef
- **AND** 清空消息列表
- **AND** appState 切换为 'empty'

### Requirement: Sidebar Collapse

系统 SHALL 支持侧边栏折叠/展开，折叠时仅显示菜单按钮。

#### Scenario: 折叠侧边栏

- **GIVEN** 侧边栏处于展开状态（宽度 256px）
- **WHEN** 用户点击关闭按钮或菜单切换按钮
- **THEN** 侧边栏折叠为窄条（宽度 48px），仅显示菜单按钮
- **AND** 主内容区域左边距相应调整

#### Scenario: 展开侧边栏

- **GIVEN** 侧边栏处于折叠状态
- **WHEN** 用户点击窄条上的菜单按钮
- **THEN** 侧边栏展开恢复完整宽度
- **AND** 主内容区域左边距相应调整

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

---

<!-- C. 深度分析流：从发起到报告生成，SSE 事件如何驱动 UI 变化 -->

### Requirement: Deep Analysis Entry

系统 SHALL 通过 POST /api/analyze 发起深度分析，请求体包含 query、api_key、user_id、analysis_type，以及可选的 session_id、stock_code、stock_name、focus。

#### Scenario: 从空状态发起深度分析

- **GIVEN** 空状态首页，模式为 'deep'，API Key 已配置
- **WHEN** 用户输入文本并发送
- **THEN** 向 POST /api/analyze 发起请求，body 包含 query、api_key、user_id、analysis_type='comprehensive'
- **AND** appState 从 'empty' 切换到 'clarifying'
- **AND** 用户消息添加到消息列表

#### Scenario: 澄清阶段后续发送

- **GIVEN** appState 为 'clarifying' 或 'report'，已有 currentSessionId
- **WHEN** 用户在底部输入栏输入文本并发送
- **THEN** 向 POST /api/analyze 发起请求，body 包含当前 session_id
- **AND** 用户消息添加到消息列表

### Requirement: Clarification Conversation Flow

深度模式下，系统 SHALL 将意图澄清阶段的交互（search_stock、web_search、thinking）走对话消息流，不触发管线 UI。仅当 Agent 调用 run_deep_analysis 工具时才进入管线 UI。澄清阶段的思考/工具调用按时间序列写入对话流消息的 `agentTimeline`。

> 来源：ADR-0017 D1 - 深度模式入口统一走 ReAct Agent 对话流

#### Scenario: 澄清阶段走对话流

- **GIVEN** 深度分析 SSE 流进行中，尚未收到 run_deep_analysis tool_call
- **WHEN** 收到 search_stock / web_search / batch_web_search 的 tool_call 事件
- **THEN** 工具调用作为 `{type:'tool_call', ...}` TimelineItem 追加到对话流消息的 `agentTimeline`，不创建管线消息
- **AND** appState 保持 'clarifying'

#### Scenario: 思考过程在澄清阶段走对话流

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（未进入管线模式）
- **WHEN** 收到 thinking_token 事件（来源为 LLM 原生 reasoning_content）
- **THEN** 思考 token 追加到对话流消息 `agentTimeline` 末尾的 thinking item（若末尾非 thinking item 则新建），不写入管线消息

#### Scenario: Agent 文本回复走对话流

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空
- **WHEN** 收到 chat_token 事件
- **THEN** token 追加到助手消息的 chatResponse（对话流）

#### Scenario: awaiting_input 切换到澄清等待

- **GIVEN** 深度分析 SSE 流进行中
- **WHEN** 收到 awaiting_input 事件
- **THEN** appState 切换为 'clarifying'
- **AND** 助手消息停止流式状态（streaming = false）

#### Scenario: run_deep_analysis 触发管线 UI

- **GIVEN** 深度分析 SSE 流进行中
- **WHEN** 收到 tool_call 事件且 name 为 'run_deep_analysis'
- **THEN** 创建管线消息（pipelineMsg），内容为"开始深度分析..."
- **AND** appState 切换为 'analyzing'
- **AND** 后续的 parsing/resolved/node_start/node_complete/report_chunk/report_ready 事件写入管线消息

### Requirement: SSE Event: session_created

系统 SHALL 在收到 session_created 事件时设置当前会话 ID 并刷新会话列表。

#### Scenario: 会话创建事件处理

- **GIVEN** 深度分析 SSE 流进行中
- **WHEN** 收到 session_created 事件
- **THEN** 设置 currentSessionId 为事件中的 session_id
- **AND** 调用 loadSessions() 刷新侧边栏会话列表

### Requirement: SSE Event: stock_resolved

系统 SHALL 在收到 stock_resolved 事件时，根据当前是否处于管线模式分别处理。

#### Scenario: 管线模式下股票识别

- **GIVEN** pipelineMsgRef 不为空（已进入管线模式）
- **WHEN** 收到 stock_resolved 事件
- **THEN** 更新管线消息内容为"已识别：{stock_name} ({stock_code})"

#### Scenario: 澄清阶段股票识别

- **GIVEN** pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 stock_resolved 事件
- **THEN** 将识别结果作为 search_stock 工具的 `{type:'tool_call', name:'search_stock', ...}` TimelineItem 追加到对话流消息的 `agentTimeline`

### Requirement: SSE Event: search_result (Deep Mode)

系统 SHALL 在深度分析澄清阶段收到 search_result 事件时，更新对话流消息 `agentTimeline` 中对应 search TimelineItem 的结果与状态，由独立搜索横幅展示，与快速模式保持一致的 Kimi-style 交互。

#### Scenario: 搜索结果由独立搜索横幅展示

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 search_result 事件
- **THEN** 对话流消息 `agentTimeline` 中对应 `{type:'search', ...}` item 的 status 设为 'done'，results 设为事件中的结果列表
- **AND** 渲染独立搜索横幅，显示"搜索了 N 个网页"
- **AND** 搜索横幅可展开查看网页列表（标题 + URL + 摘要 + favicon）
- **AND** 不将搜索结果摘要附加到工具调用横幅

### Requirement: Deep Mode Search Banner

系统 SHALL 在深度分析澄清阶段将搜索结果生成为 `search` 类型 TimelineItem，渲染为独立的搜索横幅，与快速模式保持一致的 Kimi-style 交互，按 `agentTimeline` 数组顺序排列。

#### Scenario: 澄清阶段搜索结果以搜索横幅展示

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 `search_result` 事件
- **THEN** 更新 `agentTimeline` 中对应 search item 的 `status='done'`，`results` 设为事件中的结果列表
- **AND** 渲染为独立 SearchBanner，显示"搜索了 N 个网页"
- **AND** SearchBanner 可展开查看网页列表（标题 + URL + 摘要 + favicon）

#### Scenario: 澄清阶段搜索开始显示搜索中状态

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 `search_start` 事件
- **THEN** 新建 `{type:'search', query, status:'searching'}` item 追加到 `agentTimeline`
- **AND** 渲染为独立 SearchBanner，显示"正在搜索网页"（可附查询词）
- **AND** 不显示"思考中"

### Requirement: Pipeline Progress Display

系统 SHALL 在深度分析期间以**分层时间轴**展示管线进度：顶层为 6 个 layer 节点（PREP / Layer I / Layer II / Trader / Risk / Fund），每个 layer 可展开显示其子节点列表。每个 layer 与子节点 SHALL 显示状态图标（等待/运行/完成/失败）与耗时，当前运行的子节点 SHALL 显示已运行时长并被高亮。无论 fast path 还是 agent 路径，后端 SHALL 为每个图节点发送 `node_start` 与 `node_complete` 事件对。节点计时 SHALL 优先使用后端提供的真实生命周期时间戳（server_start_ts / server_end_ts / server_duration_ms）；当后端未提供时（stub、fast path、历史会话），SHALL 回退到前端事件到达时间戳计算，保持向后兼容。

#### Scenario: 分层时间轴结构

- **GIVEN** 深度分析管线 UI 已渲染
- **THEN** 展示 6 个 layer 节点：PREP、Layer I、Layer II、Trader、Risk、Fund Manager
- **AND** 每个 layer 节点显示状态图标（○ 等待 / ◐ 运行 / ●✓ 完成 / ✗ 失败）、层名与层耗时
- **AND** 展开的 layer 内按执行顺序列出子节点（角色名中文化），各显示状态图标与节点耗时

#### Scenario: layer 与子节点映射

- **GIVEN** 分层时间轴已渲染
- **THEN** PREP 子节点为 check_cache、fetch_data、compute_metrics、validate_financials、verify_citations
- **AND** Layer I 子节点为 fundamental_analyst、technical_analyst、macro_analyst、sentiment_analyst（并行）
- **AND** Layer II 子节点为 bull_r1、bear_r1、bull_r2、bear_r2、research_manager
- **AND** Trader 子节点为 trader，Risk 子节点为风控辩论各节点，Fund 子节点为 fund_manager

#### Scenario: 节点开始时更新状态

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 node_start 事件
- **THEN** 对应子节点状态更新为 'running'，所在 layer 状态更新为 'running'
- **AND** 该子节点显示已运行时长（每秒刷新）
- **AND** 该子节点所在 layer 自动展开并高亮当前节点

#### Scenario: 节点完成时更新状态

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 node_complete 事件
- **THEN** 对应子节点状态更新为 'completed'，显示节点总耗时
- **AND** 该 layer 全部子节点完成时，layer 状态更新为 'completed' 并显示层总耗时
- **AND** 整体进度条按已完成节点数/总节点数更新

#### Scenario: Layer I 并行分析师独立状态

- **GIVEN** 管线进入 Layer I，4 个分析师并行执行
- **WHEN** 收到某分析师（如 fundamental_analyst）的 node_start / node_complete
- **THEN** 仅该分析师子节点状态更新，其余分析师状态不受影响
- **AND** 各分析师完成后显示各自的一句话摘要（来自 node_complete 内容），摘要与分析师角色对应不错位

#### Scenario: layer 展开折叠行为

- **GIVEN** 管线运行中
- **THEN** 当前运行 layer 默认展开，已完成 layer 默认折叠（显示层摘要行），未到 layer 折叠
- **WHEN** 用户手动展开/折叠某 layer
- **THEN** 本次会话内记住该偏好，不再自动改变该 layer 展开状态

#### Scenario: 自动滚动定位当前节点

- **GIVEN** 管线运行中，时间轴内容超出可视区域
- **WHEN** 当前运行节点切换
- **THEN** 时间轴平滑滚动使新当前节点进入可视区域
- **AND** 若用户最近 3 秒内手动滚动过，则暂停自动滚动

#### Scenario: agent 路径发送 node_start

- **GIVEN** 深度分析经 agent 路径（harness ReAct）执行 run_deep_analysis 流式工具
- **WHEN** graph.stream 迭代中某图节点的 updates chunk 首次出现
- **THEN** 后端 SHALL 先发送该节点的 node_start 事件（携带 node、layer、desc），再发送 node_complete
- **AND** 同一节点重复出现时不重复发送 node_start
- **AND** Layer I 并行分析师各自的 chunk 拆分发送独立节点事件；无法拆分时回退整层 node_complete

#### Scenario: 节点计时优先使用后端真实时间戳

- **GIVEN** 管线 UI 已渲染且收到 node_complete 事件
- **WHEN** 该事件携带 server_duration_ms（或 server_start_ts + server_end_ts）
- **THEN** 对应节点的 durationMs SHALL 采用后端真实耗时
- **AND** 快速节点显示真实毫秒级耗时（<1s 时 formatDurationMs 显示 "0:00"）
- **AND** 慢节点（LLM）显示真实秒级耗时

#### Scenario: 节点开始时间戳优先使用后端入口时间

- **GIVEN** 收到 node_start 事件
- **WHEN** 该事件携带 server_start_ts
- **THEN** 节点的 startedAt SHALL 采用 server_start_ts 而非前端 Date.now()
- **AND** 当前运行节点的实时已运行时长基于该时间戳计算

#### Scenario: 无后端时间戳时回退前端计算

- **GIVEN** 收到 node_complete 事件
- **WHEN** 该事件未携带任何 server_* 时间戳字段（stub / fast path / 历史会话）
- **THEN** 前端 SHALL 回退到现有 Date.now() 到达时间戳计算 durationMs
- **AND** 现有 E2E 与单测行为不回归

### Requirement: Pipeline Message Visibility Filter

系统 SHALL 仅在 appState 为 'analyzing' 时显示 pipeline 类型的消息，其他状态下隐藏。

#### Scenario: 分析中显示管线消息

- **GIVEN** appState 为 'analyzing'
- **WHEN** 渲染消息列表
- **THEN** pipeline 类型的消息显示在列表中

#### Scenario: 非分析状态隐藏管线消息

- **GIVEN** appState 为 'report' 或 'clarifying'
- **WHEN** 渲染消息列表
- **THEN** pipeline 类型的消息从列表中过滤掉，不显示

### Requirement: Pipeline Thinking Display

系统 SHALL 将各 agent 的思考过程归入分层时间轴的对应子节点下展示。当前运行节点 SHALL 内联显示实时思考摘要（单行预览），点击可展开完整 timeline；已完成节点的思考折叠到节点条目下。

#### Scenario: 当前节点内联实时思考摘要

- **GIVEN** 管线运行中，节点 N 为当前 running 节点
- **WHEN** 收到节点 N 的 thinking_token 事件
- **THEN** 节点 N 条目下方内联显示最新思考内容单行预览（流式更新，超长截断）

#### Scenario: 展开节点完整思考

- **GIVEN** 管线 UI 已渲染，节点 N 有思考内容
- **WHEN** 用户点击节点 N 条目
- **THEN** 展开该节点的完整 timeline（思考/搜索/工具调用横幅按时间序列）
- **AND** 再次点击折叠

#### Scenario: 节点完成时思考横幅显式折叠

- **GIVEN** 管线运行中，节点 N 的 thinking item 处于流式活动态
- **WHEN** 收到节点 N 的 node_complete 事件
- **THEN** 节点 N timeline 末尾的 thinking item 置为完成态（done=true）并折叠为"思考已完成"样式

#### Scenario: 下一节点思考开始时上一节点横幅收口

- **GIVEN** 管线运行中，节点 A 的 thinking item 因故未收到 node_complete 收口
- **WHEN** 收到节点 B（B ≠ A）的 thinking_token 事件
- **THEN** 节点 A 末尾未完成的 thinking item 置为完成态并折叠

#### Scenario: 历史会话兼容

- **GIVEN** 加载无节点级事件数据的旧会话
- **WHEN** 渲染管线消息
- **THEN** 回退为按既有 agentTimeline 分组渲染（角色名标题分隔），不报错

### Requirement: Pipeline Expandable Log

系统 SHALL 在管线 UI 中提供可展开的实时输出日志，展示已完成节点的摘要。

#### Scenario: 查看实时日志

- **GIVEN** 管线 UI 已渲染
- **WHEN** 用户点击"查看实时输出日志"
- **THEN** 展开日志区域，显示所有已完成节点的记录（节点名、时间戳、摘要）
- **AND** 若有当前运行节点，显示运行中指示器

### Requirement: Report Streaming Render

系统 SHALL 在深度分析管线完成后，通过 report_chunk 事件渐进渲染报告，最终由 report_ready 事件完成。

#### Scenario: 报告流式分块累积

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 report_chunk 事件
- **THEN** 若尚无报告消息，创建一条 streaming=true 的报告消息，初始内容为事件文本
- **AND** 若已有报告消息，将事件文本追加到 reportMarkdown
- **AND** 报告消息显示"正在生成报告"流式指示器

#### Scenario: 报告就绪完成渲染

- **GIVEN** 报告消息正在流式生成
- **WHEN** 收到 report_ready 事件
- **THEN** 更新报告消息：reportMarkdown 替换为最终完整版、chartData、filePaths、stockName、durationMs、sessionId、webSources，streaming=false
- **AND** appState 切换为 'report'
- **AND** 设置 currentSessionId 为事件中的 session_id
- **AND** 刷新侧边栏会话列表
- **AND** 添加系统消息"分析完成 · 耗时 {N} 秒"

#### Scenario: 无流式分块直接就绪

- **GIVEN** 管线 UI 已渲染，尚未收到任何 report_chunk
- **WHEN** 直接收到 report_ready 事件
- **THEN** 创建一条完整的报告消息（streaming=false），包含所有最终数据

---

<!-- D. 快速对话流：快速模式的入口和搜索结果展示 -->

### Requirement: Quick Chat Entry

系统 SHALL 通过 POST /api/chat 发起快速对话，请求体包含 message、user_id、api_key，以及可选的 session_id。

#### Scenario: 从空状态发起快速对话

- **GIVEN** 空状态首页，模式为 'quick'，API Key 已配置
- **WHEN** 用户输入文本并发送
- **THEN** 向 POST /api/chat 发起请求，body 包含 message、user_id、api_key
- **AND** appState 从 'empty' 切换到 'clarifying'
- **AND** 用户消息和助手消息（streaming=true）添加到消息列表

#### Scenario: 对话中后续发送

- **GIVEN** appState 为 'clarifying' 或 'report'，已有 currentSessionId
- **WHEN** 用户在底部输入栏输入文本并发送
- **THEN** 向 POST /api/chat 发起请求，body 包含当前 session_id
- **AND** 用户消息和助手消息（streaming=true）添加到消息列表

### Requirement: Quick Chat Search Events

系统 SHALL 在快速模式下处理搜索类 SSE 事件，生成 `search` 类型 TimelineItem，渲染为独立的可折叠搜索横幅（SearchBanner），按 `agentTimeline` 数组顺序排列。

#### Scenario: 搜索开始显示搜索中状态

- **GIVEN** 快速对话 SSE 流进行中
- **WHEN** 收到 `search_start` 事件
- **THEN** 新建 `{type:'search', query, status:'searching'}` item 追加到 `agentTimeline`
- **AND** 对应 SearchBanner 显示"正在搜索网页"（可附查询词），脉冲动画指示搜索进行中
- **AND** 不显示"思考中"

#### Scenario: 搜索完成展示结果

- **GIVEN** `agentTimeline` 中某 search item `status='searching'`
- **WHEN** 收到 `search_result` 事件
- **THEN** 更新该 item `status='done'`，`results` 设为事件中的结果列表
- **AND** 对应 SearchBanner 显示"搜索了 N 个网页"（N 为结果数量）
- **AND** SearchBanner 可展开，展开后显示网页列表，每条包含序号、标题、摘要、域名、favicon

#### Scenario: 搜索失败显示错误状态

- **GIVEN** `agentTimeline` 中某 search item `status='searching'`
- **WHEN** 收到 `search_error` 事件
- **THEN** 更新该 item `status='error'`
- **AND** 对应 SearchBanner 显示搜索失败状态

#### Scenario: 搜索横幅可折叠

- **GIVEN** SearchBanner 已渲染（status='done'）
- **WHEN** 用户点击搜索横幅标题
- **THEN** 切换该横幅的展开/折叠状态
- **AND** 折叠时仅显示"搜索了 N 个网页"摘要行
- **AND** 展开时显示完整网页列表

---

<!-- E. 对话流公共机制：两种模式共用的思考/工具/错误处理和 SSE 中断逻辑 -->

### Requirement: Conversation Stream Common Events

系统 SHALL 在深度模式的澄清阶段和快速模式中共用同一套对话流事件处理逻辑，将 thinking、search、tool_call、chat 类事件写入 `agentTimeline` 数组（按事件时序）和 `chatResponse`（回答正文）。思考内容来源于 DeepSeek 原生 `reasoning_content`（通过 `thinking_token` 事件下发），与回答内容（`chat_token` 事件）天然分离，不再使用 `thinking_to_answer` 剥离机制。搜索类工具（`web_search` / `batch_web_search`）的调用与结果 SHALL NOT 进入工具调用横幅，仅由独立搜索横幅承载。思考横幅 SHALL 在思考结束（出现后续事件）时显式置为完成态并自动折叠。

#### Scenario: thinking_token 累积原生思考内容

- **GIVEN** 对话流进行中
- **WHEN** 收到 `thinking_token` 事件（来源为 LLM 原生 `reasoning_content`）
- **THEN** 若 `agentTimeline` 末尾是 `thinking` 类型 item，将 token 累加到该 item 的 `content`
- **AND** 否则新建 `{type:'thinking', content: token, done:false}` item 追加到 `agentTimeline`
- **AND** 思考链（thinking）是独立的思维内容，与回答（`chatResponse`，content）分离

#### Scenario: 思考后接工具调用时思考横幅折叠

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是未完成（done=false）的 thinking item
- **WHEN** 收到 `tool_call` 事件
- **THEN** 该 thinking item 置为完成态（done=true）
- **AND** ThinkingBanner 从"思考中"切换为"思考已完成"并自动折叠

#### Scenario: 思考后接回答 token 时思考横幅折叠

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是未完成（done=false）的 thinking item
- **WHEN** 收到首个 `chat_token` 事件
- **THEN** 该 thinking item 置为完成态（done=true）并自动折叠

#### Scenario: thinking_to_answer 事件不再下发

- **GIVEN** 对话流进行中，LLM 输出 reasoning_content 后输出 content
- **WHEN** 思考与回答流式下发完成
- **THEN** SHALL NOT 收到 thinking_to_answer 事件（reasoning 与 content 天然分离）
- **AND** 前端无需执行思考剥离为回答的逻辑

#### Scenario: thinking_replace 事件不再下发

- **GIVEN** 对话流进行中
- **WHEN** LLM 原生 reasoning_content 流式输出
- **THEN** SHALL NOT 收到 thinking_replace 事件（原生 reasoning 无需 DSML 清理后处理）
- **AND** 思考内容直接流式展示，无需覆盖

#### Scenario: tool_call 记录到工具调用横幅

- **GIVEN** 对话流进行中
- **WHEN** 收到 `tool_call` 事件，且 name 不为 `run_deep_analysis`、`web_search`、`batch_web_search`
- **THEN** 新建 `{type:'tool_call', name, args, done:false}` item 追加到 `agentTimeline`，渲染为 ToolCallEntry（含图标、标签、参数摘要、done=false）
- **AND** 工具调用与思考过程分离展示

#### Scenario: 搜索类 tool_call 不进入工具调用横幅

- **GIVEN** 对话流进行中
- **WHEN** 收到 `tool_call` 事件，且 name 为 `web_search` 或 `batch_web_search`
- **THEN** SHALL NOT 在 `agentTimeline` 创建 tool_call item / ToolCallEntry
- **AND** 该工具的状态与结果由 `search_start` / `search_result` 事件驱动搜索横幅展示
- **AND** 不触发管线 UI

#### Scenario: tool_result 附加到对应工具调用

- **GIVEN** 对话流进行中，助手消息已有工具调用记录
- **WHEN** 收到 `tool_result` 事件
- **THEN** 若事件对应 `web_search` / `batch_web_search` 工具，SHALL NOT 附加到任何工具调用记录、SHALL NOT 新建记录（其结果由 `search_result` 事件驱动搜索横幅展示）
- **AND** 否则，优先附加到同名且未完成的最近一次工具调用记录（设 `result` 和 `done=true`）
- **AND** 若无同名未完成记录，回退到最近未完成的任意工具调用
- **AND** 若该记录已完成（已被 search_result/stock_resolved 等结构化事件先行附加），跳过避免重复
- **AND** 若无任何匹配记录且结果非空，新建一条仅含结果的工具调用记录

#### Scenario: search 事件生成 search item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `search_start` / `search_result` / `search_error` 事件
- **THEN** 新建或更新 `search` 类型 TimelineItem（见 Agent Timeline Display 需求）
- **AND** 搜索类工具不生成 tool_call item

#### Scenario: chat_token 累积回答

- **GIVEN** 对话流进行中
- **WHEN** 收到 `chat_token` 事件（来源为 LLM content，与 reasoning 分离）
- **THEN** token 追加到助手消息的 `chatResponse`

#### Scenario: chat_done 结束流式

- **GIVEN** 对话流进行中，助手消息 streaming=true
- **WHEN** 收到 `chat_done` 事件
- **THEN** 助手消息 streaming 设为 false
- **AND** 所有 thinking item 置为完成态（done=true），用 `extractThinkingTitle` 提取标题写入 `title` 字段

#### Scenario: 对话流 error 事件

- **GIVEN** 对话流进行中
- **WHEN** 收到 `error` 事件
- **THEN** 助手消息 `chatResponse` 设为"❌ {message}"，streaming 设为 false
- **AND** 所有未完成 thinking item 置为完成态（done=true）

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

### Requirement: Deep Mode chat_done Event Routing

深度模式（`startAnalysis`）的 SSE 事件循环 SHALL 将 `chat_done` 事件路由到对话流共享处理函数（`handleChatStreamEvent`），与快速模式（`quickChat`）保持一致。`chat_done` 事件经 `applyChatStreamEvent` 处理后 SHALL 将助手消息 `streaming` 置为 false 并收口所有 thinking item。

#### Scenario: 深度模式澄清阶段收到 chat_done 清除流式状态

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段），助手消息 streaming=true
- **WHEN** 收到 `chat_done` 事件
- **THEN** 事件 SHALL 经 `handleChatStreamEvent` 处理，助手消息 streaming 置为 false
- **AND** 所有 thinking item 收口并提取标题写入 title 字段
- **AND** 流式游标消失

#### Scenario: 深度模式管线运行期间不误处理 chat_done

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 不为空（管线模式）
- **WHEN** 收到 `chat_done` 事件
- **THEN** 事件 SHALL 经 `handleChatStreamEvent` 处理（写入对话流消息 timeline）
- **AND** 管线消息不受影响，管线进度继续由管线事件驱动

### Requirement: Deep Mode Error Handling

系统 SHALL 在深度分析流的 error 事件中，根据是否处于管线模式分别处理错误展示。

#### Scenario: 管线模式下的错误

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 不为空
- **WHEN** 收到 error 事件
- **THEN** 管线消息类型更新为 'error'，内容为"错误: {message}"

#### Scenario: 非管线模式下的错误

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空
- **WHEN** 收到 error 事件
- **THEN** 添加一条 error 类型的消息到消息列表，内容为"错误: {message}"

---

<!-- F. 渲染与展示：报告卡片、思考横幅、工具调用横幅等 UI 组件的渲染规则 -->

### Requirement: Report Card Rendering

系统 SHALL 在报告消息中渲染报告头部、文件导出入口、财务图表、Markdown 正文、参考资料和免责声明。

#### Scenario: 流式报告显示生成指示器

- **GIVEN** 报告消息 streaming=true
- **THEN** 顶部显示"正在生成报告 · 流式输出中"指示器（脉冲动画）

#### Scenario: 报告头部展示

- **GIVEN** 报告消息 streaming=false
- **THEN** 显示股票名称（stockName）、"深度分析"标签、耗时信息
- **AND** 报告头部显示「全部文件」入口横幅（图标 + "全部文件"文案），点击可打开文件导出抽屉

#### Scenario: 打开导出抽屉

- **GIVEN** 报告头部已渲染，展示「全部文件」入口横幅
- **WHEN** 用户点击「全部文件」横幅
- **THEN** 右侧文件导出抽屉滑出打开
- **AND** 抽屉内列出该报告当前可用的导出文件（依据 filePaths 的 docx/pptx/pdf/md 键，带格式徽标与文件名）

#### Scenario: 财务图表展示

- **GIVEN** 报告消息包含 chartData 且 chartData.annual 非空
- **THEN** 在报告头部下方渲染 ChartsSection（ECharts 交互图表）

#### Scenario: Markdown 正文渲染

- **GIVEN** 报告消息包含 reportMarkdown
- **THEN** 使用 react-markdown + remark-gfm 渲染 Markdown
- **AND** 图片标签（img）被忽略不渲染
- **AND** 链接在新标签页打开
- **AND** 渲染区域最大高度 600px，可滚动

#### Scenario: 参考资料信源卡片

- **GIVEN** 报告消息 streaming=false 且包含 webSources（非空数组）
- **THEN** 在 Markdown 正文下方渲染信源卡片网格
- **AND** 每张卡片显示序号、标题、摘要、域名、favicon
- **AND** 标题显示"参考资料（N 个信源）"

#### Scenario: 免责声明

- **GIVEN** 报告消息 streaming=false
- **THEN** 在底部显示免责声明"本报告由 AI 系统基于公开数据自动生成，仅供参考研究，不构成投资建议。投资有风险，入市需谨慎。"

### Requirement: Agent Timeline Display

系统 SHALL 将助手消息内的思考、搜索、工具调用按 SSE 事件到达的真实时序纵向排列，存储为 `agentTimeline: TimelineItem[]` 数组，替代原有的分离字段（`thinkingContent` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls`）。每个 TimelineItem 渲染为对应类型的独立可折叠横幅，response（chatResponse）在 timeline 之后以 Markdown 渲染，不框起。

#### Scenario: TimelineItem 联合类型定义

- **GIVEN** 助手消息的数据结构
- **THEN** `UIMessage` SHALL 包含 `agentTimeline: TimelineItem[]` 字段
- **AND** `TimelineItem` 为联合类型，包含三种：
  - `{type:'thinking', content: string, title?: string}` 思考片段
  - `{type:'search', query: string, results?: Array<{title,url,content}>, status: 'searching'|'done'|'error'}` 搜索
  - `{type:'tool_call', name: string, args: string, result?: string, done: boolean}` 其他工具调用
- **AND** 废弃分离字段 `thinkingContent` / `thinkingTitle` / `searchStatus` / `searchResults` / `searchQuery` / `toolCalls`

#### Scenario: 按 SSE 事件时序追加 TimelineItem

- **GIVEN** 对话流（快速模式或深度模式澄清阶段）进行中
- **WHEN** 收到 `thinking_token` / `search_start` / `search_result` / `search_error` / `tool_call` / `tool_result` 事件
- **THEN** 按事件到达顺序向 `agentTimeline` 数组追加或更新 TimelineItem
- **AND** 渲染顺序与 `agentTimeline` 数组顺序一致，反映 agent 实际执行时序

#### Scenario: 思考片段断开逻辑

- **GIVEN** 对话流进行中，`agentTimeline` 数组已存在
- **WHEN** 收到 `thinking_token` 事件
- **THEN** 若 `agentTimeline` 末尾是 `thinking` 类型 item，则将该 token 累加到该 item 的 `content`
- **AND** 若 `agentTimeline` 末尾是 `search` 或 `tool_call` 类型 item，或 timeline 为空，则新建一个 `thinking` item 追加到数组末尾
- **AND** 同一段思考流式累加，遇到 `tool_call` / `search_start` 事件则断开成新思考片段

#### Scenario: 每个 TimelineItem 渲染为独立可折叠横幅

- **GIVEN** 助手消息包含 `agentTimeline` 数组
- **WHEN** 渲染助手消息
- **THEN** 遍历 `agentTimeline`，按 `item.type` 分发渲染：
  - `thinking` -> 渲染为独立的 ThinkingBanner（可折叠，标题由该段思考独立提取）
  - `search` -> 渲染为独立的 SearchBanner（可折叠，显示搜索状态/查询/结果）
  - `tool_call` -> 渲染为独立的 ToolCallBanner（可折叠，单条目）
- **AND** 每个横幅独立管理自己的折叠/展开状态
- **AND** 横幅之间无外层汇总折叠框，无汇总标题

#### Scenario: Response 在 timeline 之后不框起

- **GIVEN** 助手消息包含 `agentTimeline` 和 `chatResponse`
- **WHEN** 渲染助手消息
- **THEN** `agentTimeline` 的所有横幅渲染在前
- **AND** `chatResponse` 在所有横幅之后以 Markdown 渲染
- **AND** `chatResponse` 不被任何框体包裹，直接展示为正文

#### Scenario: 工具执行期间各横幅显示对应状态文案

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是 `search` 类型 item 且 `status='searching'`
- **THEN** 对应 SearchBanner 显示"正在搜索网页"（脉冲动画），而非"思考中"
- **AND** 思考横幅（若有未完成的 thinking item）在该期间不显示"思考中"（agent 当前在执行搜索而非思考）

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是 `tool_call` 类型 item 且 `done=false`
- **THEN** 对应 ToolCallBanner 显示"正在调用工具"（脉冲动画），而非"思考中"
- **AND** 思考横幅（若有未完成的 thinking item）在该期间不显示"思考中"（agent 当前在调用工具而非思考）

#### Scenario: 思考横幅仅在 agent 实际思考时显示"思考中"

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是 `thinking` 类型 item 且正在流式接收 `thinking_token`
- **THEN** 该 ThinkingBanner 显示"思考中"（脉冲动画）
- **AND** 当 agent 转为执行搜索或工具调用（timeline 末尾变为 search/tool_call item）时，该 ThinkingBanner 不再显示"思考中"

#### Scenario: 搜索事件生成 search 类型 item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `search_start` 事件
- **THEN** 新建 `{type:'search', query, status:'searching'}` item 追加到 `agentTimeline`
- **WHEN** 收到 `search_result` 事件
- **THEN** 更新该 search item 的 `status` 为 'done'，`results` 设为事件中的结果列表
- **WHEN** 收到 `search_error` 事件
- **THEN** 更新该 search item 的 `status` 为 'error'
- **AND** `web_search` / `batch_web_search` 不生成 `tool_call` 类型 item（沿用 isSearchTool 过滤逻辑）

#### Scenario: 其他工具调用生成 tool_call 类型 item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `tool_call` 事件（非 run_deep_analysis，非搜索类工具）
- **THEN** 新建 `{type:'tool_call', name, args, done:false}` item 追加到 `agentTimeline`
- **WHEN** 收到 `tool_result` 事件
- **THEN** 更新对应 tool_call item 的 `result` 和 `done=true`
- **AND** 每次 tool call 生成独立的 tool_call item（不合并到同一横幅）

#### Scenario: 管线模式按 agent 阶段分组 timeline

- **GIVEN** 管线 UI 已渲染（深度分析模式）
- **WHEN** 渲染管线消息
- **THEN** 保留阶段进度条（6 阶段：PREP、Layer I、Layer II、Trader、Risk、Fund Manager）
- **AND** 每个 agent 阶段的 timeline items 归在该阶段下，阶段间用角色名标题分隔（非折叠框，纯文本标题）
- **AND** 阶段内按时间序列排列该 agent 的思考/搜索/工具调用横幅
- **AND** 当前活动阶段的横幅展开，已完成阶段的横幅折叠

#### Scenario: 历史会话恢复重建 agentTimeline

- **GIVEN** 加载已有会话，从 `chat_history` 恢复助手消息
- **WHEN** 构建助手消息的 `agentTimeline`
- **THEN** 从 `chat_history.thinking`（合并字符串）构建 thinking item
- **AND** 从 `chat_history.tool_calls`（数组）按序构建 tool_call items
- **AND** 按"思考在前、工具调用在后"的顺序排列（历史数据无完整时序信息，近似还原）
- **AND** 每个 thinking item 独立用 `extractThinkingTitle` 提取标题

### Requirement: Thinking Banner Display

系统 SHALL 在助手消息中将思考过程展示为可折叠横幅，每个思考片段（TimelineItem type='thinking'）独立一个横幅实例。流式时自动展开，完成后可手动折叠。标题展示规则沿用 thinking-stream-banner-display 变更：思考中显示"思考中"（脉冲动画）；完成折叠态有标题显示标题、无标题显示"思考已完成"；完成展开态固定"思考已完成"，框内标题加粗置顶（若有）。

#### Scenario: 流式思考自动展开

- **GIVEN** 助手消息 streaming=true，`agentTimeline` 末尾是 `thinking` 类型 item 且有 content
- **THEN** 该 ThinkingBanner 自动展开，显示脉冲动画指示"思考中"
- **AND** 内容区域自动滚动到底部
- **AND** 仅当 agent 实际在思考（timeline 末尾为 thinking item）时显示"思考中"；当 agent 转为执行搜索/工具调用时，该横幅不再显示"思考中"

#### Scenario: 思考完成折叠态有标题

- **GIVEN** 助手消息 streaming 从 true 变为 false，某 thinking item 的 `title` 非空
- **AND** 该 ThinkingBanner 处于折叠状态
- **THEN** 脉冲动画停止，显示勾选图标
- **AND** 横幅标题显示该 thinking item 的 `title`
- **AND** 不显示"· {N} 字"字数信息

#### Scenario: 思考完成折叠态无标题

- **GIVEN** 助手消息 streaming 从 true 变为 false，某 thinking item 的 `title` 为空
- **AND** 该 ThinkingBanner 处于折叠状态
- **THEN** 脉冲动画停止，显示勾选图标
- **AND** 横幅标题显示"思考已完成"

#### Scenario: 思考完成展开态

- **GIVEN** 助手消息 streaming 从 true 变为 false
- **AND** 某 ThinkingBanner 处于展开状态
- **THEN** 横幅标题固定显示"思考已完成"（不论是否有标题）
- **AND** 框内若该 thinking item 有 `title`，将标题以加粗样式置顶展示于思考正文之上
- **AND** 思考正文按 Markdown 渲染（支持 `##` 层级标题与 `**加粗**` 分段）

#### Scenario: 多段思考独立横幅

- **GIVEN** `agentTimeline` 包含多个 `thinking` 类型 item（被工具调用断开）
- **WHEN** 渲染助手消息
- **THEN** 每个 thinking item 渲染为独立的 ThinkingBanner 实例
- **AND** 每个 ThinkingBanner 独立提取标题、独立管理折叠状态
- **AND** 横幅按 `agentTimeline` 数组顺序纵向排列

#### Scenario: 手动折叠/展开

- **GIVEN** ThinkingBanner 已渲染
- **WHEN** 用户点击横幅标题
- **THEN** 切换该横幅的展开/折叠状态
- **AND** 折叠时内容区域高度为 0，展开时最大高度 240px
- **AND** 其他横幅的折叠状态不受影响

### Requirement: Tool Call Banner Display

系统 SHALL 在助手消息中将每次工具调用展示为独立的可折叠横幅（TimelineItem type='tool_call'），与思考过程分离。每个 tool_call item 渲染为一个独立的 ToolCallBanner 实例（单条目），按 `agentTimeline` 数组顺序排列。

#### Scenario: 每次工具调用独立横幅

- **GIVEN** `agentTimeline` 包含 `tool_call` 类型 item
- **WHEN** 渲染助手消息
- **THEN** 每个 tool_call item 渲染为独立的 ToolCallBanner 实例
- **AND** 显示工具图标、标签、参数摘要
- **AND** 已完成的工具调用显示结果摘要
- **AND** 未完成的工具调用显示"执行中..."旋转动画
- **AND** 横幅按 `agentTimeline` 数组顺序排列（穿插在 thinking item 之间）

#### Scenario: 工具调用横幅状态

- **GIVEN** 某 tool_call item `done=false`
- **THEN** 对应 ToolCallBanner 标题显示"正在调用工具"，脉冲动画
- **AND** 不显示"思考中"
- **GIVEN** 某 tool_call item `done=true`
- **THEN** 对应 ToolCallBanner 标题显示"已调用工具"，勾选图标

### Requirement: Message Auto-Scroll

系统 SHALL 在消息列表变化时自动滚动到页面底部。

#### Scenario: 新消息添加时滚动

- **GIVEN** 消息列表中有消息
- **WHEN** 消息列表发生变化（新消息添加或现有消息更新）
- **THEN** 页面平滑滚动到 body 底部

### Requirement: Chat Input Bar

系统 SHALL 在非空状态下显示固定的底部输入栏，包含模式切换、文本输入和发送功能。

#### Scenario: 底部输入栏渲染

- **GIVEN** appState 不为 'empty'
- **THEN** 底部固定显示输入栏，包含深度/快速模式切换按钮、textarea 输入框、发送按钮
- **AND** 底部显示"AI 生成仅供参考，不构成投资建议"

#### Scenario: 输入栏发送

- **GIVEN** 底部输入栏，当前模式为 'deep'
- **WHEN** 用户输入文本并按 Enter（非 Shift+Enter）
- **THEN** 调用 startAnalysis 发送文本
- **AND** 输入框清空

#### Scenario: 输入栏模式切换锁定

- **GIVEN** currentSessionId 不为 null（已有会话）
- **THEN** 模式切换按钮禁用，显示锁定图标
- **GIVEN** currentSessionId 为 null
- **THEN** 模式切换按钮可用

### Requirement: Message Type Rendering

系统 SHALL 根据消息类型（user/pipeline/report/chat/system/error）渲染不同样式的消息卡片。chat 类型消息遍历 `agentTimeline` 渲染横幅，response 在后。

#### Scenario: 用户消息右对齐

- **GIVEN** 消息类型为 'user'
- **THEN** 消息右对齐，使用品牌色背景

#### Scenario: 错误消息展示

- **GIVEN** 消息类型为 'error'
- **THEN** 消息左对齐，显示红色错误图标和错误文本

#### Scenario: 系统消息展示

- **GIVEN** 消息类型为 'system' 且内容不为 'typing'
- **THEN** 消息左对齐，显示机器人图标和成功勾选标记

#### Scenario: 助手消息按时间序列渲染

- **GIVEN** 消息类型为 'chat'
- **THEN** 消息左对齐，显示机器人图标
- **AND** 遍历 `agentTimeline` 数组，按 item.type 渲染对应横幅（ThinkingBanner / SearchBanner / ToolCallBanner）
- **AND** 横幅按 `agentTimeline` 数组顺序纵向排列
- **AND** `chatResponse` 在所有横幅之后以 Markdown 渲染，不框起
- **AND** 若 streaming=true 且无 chatResponse，在最后显示"思考中..."旋转动画

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

#### Scenario: 恢复搜索记录

- **GIVEN** 加载的会话 `chat_history` 中某条助手消息包含搜索相关记录（若后端存储）
- **WHEN** 构建助手消息
- **THEN** 构建 `{type:'search', query, results, status:'done'}` item 插入 `agentTimeline` 对应位置
- **AND** 若后端未存储搜索时序，按"思考 -> 搜索 -> 工具调用"的近似顺序排列

### Requirement: 管线时序恢复

系统 SHALL 在加载已有会话时，从会话详情的 `pipeline_timelines`（JSON：`{node: [TimelineItem]}`）恢复深度分析管线消息的 `nodeTimelines`，使各节点的思考/工具调用记录切换会话后完整可见。

#### Scenario: 切回会话恢复管线节点时序

- **GIVEN** 某深度分析会话的 pipeline_timelines 已持久化（含各节点思考/工具时序）
- **WHEN** 用户切换到该会话（运行中或已完成）
- **THEN** 前端 SHALL 反序列化 pipeline_timelines 为管线消息的 nodeTimelines
- **AND** 各节点的思考内容、网络搜索、工具调用记录按原时序展示
- **AND** 非法/缺失的 pipeline_timelines 回退为空（时间轴树仍由 pipeline_snapshot 恢复）

### Requirement: 跨会话恢复管线 UI

系统 SHALL 在用户切换会话时恢复目标会话的管线 UI 状态：运行中的管线恢复实时分层时间轴，已完成的管线恢复报告与静态分层时间轴。切换离开运行中的深度管线会话时 SHALL NOT 中断该管线（由后端后台续跑）。

#### Scenario: 切回运行中的管线会话恢复实时时间轴

- **GIVEN** 某深度分析会话的管线正在后台运行（status=running 且有 pipeline_snapshot）
- **WHEN** 用户切换到该会话
- **THEN** 前端 SHALL 从 pipeline_snapshot 重建分层时间轴（各节点 status/耗时）
- **AND** 当前运行节点 SHALL 正确高亮，其已运行时长基于 server_start_ts 实时递增
- **AND** 前端 SHALL 轮询会话快照以更新节点完成进度，直至 status 变 completed

#### Scenario: 切回已完成的管线会话恢复报告与静态时间轴

- **GIVEN** 某会话的管线已完成（status=completed）
- **WHEN** 用户切换到该会话
- **THEN** 前端 SHALL 显示报告消息（report）与已完成的静态分层时间轴
- **AND** 静态时间轴各节点 SHALL 显示真实耗时与摘要（供回看）
- **AND** 前端 SHALL NOT 继续轮询该会话快照

#### Scenario: 切换离开运行中的深度管线不中断

- **GIVEN** 某深度分析会话的管线正在运行
- **WHEN** 用户切换到其他会话
- **THEN** 前端 abortStreaming 仅断开 SSE 订阅，SHALL NOT 中断后端管线执行
- **AND** 管线在后台继续，切回时可恢复

#### Scenario: 切回失败的管线会话显示失败状态

- **GIVEN** 某会话的管线已失败（status=failed，含后端重启悬挂的 running 被标记）
- **WHEN** 用户切换到该会话
- **THEN** 前端 SHALL 显示分析失败状态而非误认为仍在运行

> **MVP 决策**：MVP 阶段 failed 分支不专门处理 UI（回退到现有 report/chat_history 恢复逻辑），失败态 UI 为后续改进。

#### Scenario: 快速模式会话切换行为不变

- **GIVEN** 用户从快速模式（chat）会话切换离开
- **WHEN** 该会话无深度管线
- **THEN** 前端维持现有 abortStreaming 行为（快速模式流无恢复价值）

### Requirement: Pipeline ETA Display

系统 SHALL 在管线进度区域显示动态预估时间，包括已用时长与预估剩余时间，替代静态文案。预估 SHALL 基于历史运行数据并随进度收敛。

#### Scenario: 显示已用时长与预估剩余

- **GIVEN** 深度分析管线运行中
- **THEN** 进度区域显示"已用时 M:SS · 预计剩余 ~M:SS"格式文本，每秒刷新
- **AND** 不显示硬编码静态预估文案（如"~90s"）

#### Scenario: 基于历史中位数的初始预估

- **GIVEN** localStorage 存在最近 N 次（最多 10 次）完整管线运行耗时记录
- **WHEN** 新一次管线启动
- **THEN** 初始预估总时长取历史记录的中位数
- **AND** 若无历史记录，使用默认值 240 秒

#### Scenario: 预估随进度线性收敛

- **GIVEN** 管线运行中，已完成节点数占比 p = completed/total
- **WHEN** 实际进度比例 p 超过 已用时长/预估总时长 所隐含的进度
- **THEN** 用 已用时长/p 重新估算总时长
- **AND** 预估剩余时间 = max(0, 重估总时长 - 已用时长)

#### Scenario: 管线完成后记录耗时

- **GIVEN** 管线运行中
- **WHEN** 收到 report_ready 事件（管线完成）
- **THEN** 将本次总耗时写入 localStorage 历史记录（最多保留 10 条，超出时淘汰最旧记录）

#### Scenario: localStorage 不可用回退

- **GIVEN** 浏览器环境 localStorage 不可用（隐私模式等）
- **THEN** 预估使用默认值 240 秒，ETA 显示功能不阻塞、不报错

