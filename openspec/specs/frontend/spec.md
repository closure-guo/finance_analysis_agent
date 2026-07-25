# Frontend Specification

> 来源：incident 010（缺少行为 spec 约束）、ADR-0012（session 流式与自然输入）、ADR-0017（意图澄清对话流）
> 基线构建日期：2026-07-24
> 说明：本 spec 从 `frontend/src/App.tsx`、`frontend/src/types.ts` 现有实现反推，捕获当前行为作为真相来源。

## Purpose

定义 React 前端（React 18 + Vite + TailwindCSS）的用户交互行为契约。覆盖空状态首页、API Key 管理、会话管理、深度/快速两种模式的 SSE 流式渲染、管线进度展示、报告渲染与文件下载。

## Requirements

> 以下是前端 33 个行为契约，按 6 个行为域分组。每组覆盖一个独立的交互主题，可独立审阅。

| 行为域 | 需求数 | 通俗说明 |
|--------|--------|----------|
| A. 首页与输入 | 5 | 用户第一次打开页面看到什么、怎么选模式、怎么配 API Key |
| B. 会话管理 | 7 | 左侧栏的会话列表：搜索、切换、删除、重命名、新建 |
| C. 深度分析流 | 9 | 深度模式的核心：从发起到报告生成，SSE 事件如何驱动 UI 变化 |
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

系统 SHALL 在用户选择已有会话时中断进行中的 SSE 流，加载该会话的完整历史并切换到报告视图。

#### Scenario: 选择会话加载历史

- **GIVEN** 侧边栏会话列表中有一个会话
- **WHEN** 用户点击该会话
- **THEN** 中断当前进行中的 SSE 流（若有）
- **AND** 向 GET /api/sessions/{sessionId} 发起请求获取会话详情
- **AND** 重置消息列表、streamingReportRef、pipelineMsgRef
- **AND** 设置 currentSessionId 并将 appState 切换为 'report'
- **AND** 按 session_type 锁定模式

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

深度模式下，系统 SHALL 将意图澄清阶段的交互（search_stock、web_search、thinking）走对话消息流，不触发管线 UI。仅当 Agent 调用 run_deep_analysis 工具时才进入管线 UI。

> 来源：ADR-0017 D1 - 深度模式入口统一走 ReAct Agent 对话流

#### Scenario: 澄清阶段走对话流

- **GIVEN** 深度分析 SSE 流进行中，尚未收到 run_deep_analysis tool_call
- **WHEN** 收到 search_stock / web_search / batch_web_search 的 tool_call 事件
- **THEN** 工具调用记录添加到助手消息的 toolCalls 列表（对话流），不创建管线消息
- **AND** appState 保持 'clarifying'

#### Scenario: 思考过程在澄清阶段走对话流

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（未进入管线模式）
- **WHEN** 收到 thinking_token / thinking_replace / thinking_to_answer 事件
- **THEN** 思考内容追加/替换到助手消息（对话流），不写入管线消息

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
- **THEN** 将识别结果作为 search_stock 工具的结构化结果附加到助手消息的 toolCalls 记录

### Requirement: SSE Event: search_result (Deep Mode)

系统 SHALL 在深度分析澄清阶段收到 search_result 事件时，将搜索结果摘要附加到助手消息的工具调用记录。

#### Scenario: 搜索结果附加到工具调用记录

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 search_result 事件
- **THEN** 将结果摘要附加到助手消息的 web_search/batch_web_search 工具调用记录
- **AND** 摘要格式为"找到 {count} 条结果：{前3条结果标题}，以、分隔"
- **AND** 结果在 ToolCallBanner 中展示（非独立搜索横幅）

### Requirement: Pipeline Progress Display

系统 SHALL 在深度分析期间展示 6 阶段管线进度，每阶段映射到后端 LangGraph 节点。

#### Scenario: 管线 6 阶段定义

- **GIVEN** 深度分析管线 UI 已渲染
- **THEN** 展示 6 个阶段节点：PREP、Layer I、Layer II、Trader、Risk、Fund Manager
- **AND** 每个阶段映射到后端节点：check_cache(PREP)、technical_analyst(Layer I)、bull_r1(Layer II)、trader(Trader)、aggressive_r1(Risk)、fund_manager(Fund Manager)

#### Scenario: 节点开始时更新阶段状态

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 node_start 事件
- **THEN** 对应阶段状态更新为 'running'，显示当前节点 ID 和层级描述
- **AND** 管线消息内容更新为"{layer}: {desc}..."

#### Scenario: 节点完成时更新进度

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 node_complete 事件
- **THEN** 对应阶段状态更新为 'completed'
- **AND** 进度条更新为事件中的 progress 值
- **AND** 节点输出记录到 nodeOutputs
- **AND** 管线消息内容更新为"{layer}: {desc} ✓"

#### Scenario: 阶段状态推断

- **GIVEN** 管线 UI 已渲染，某阶段的全部子节点均已 completed
- **THEN** 该阶段状态为 'completed'
- **WHEN** 某阶段有子节点正在 running
- **THEN** 该阶段状态为 'running'
- **AND** 其余阶段状态为 'pending'

#### Scenario: Layer I 分析师卡片展示

- **GIVEN** 管线进入 Layer I 阶段（check_cache 完成或 technical_analyst 运行中/完成）
- **THEN** 展示 4 个分析师卡片（基本面/技术面/宏观/舆情）
- **WHEN** technical_analyst 节点未完成
- **THEN** 4 个卡片状态均为 'running' 或 'pending'，摘要为"分析中..."或"等待中..."
- **WHEN** technical_analyst 节点完成
- **THEN** 4 个卡片状态均为 'completed'，摘要更新为"XX分析完成"

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

系统 SHALL 在管线 UI 中展示流式思考过程，与管线进度区域分离。

#### Scenario: 管线运行期间思考流式追加

- **GIVEN** 管线 UI 已渲染，pipelineMsgRef 不为空
- **WHEN** 收到 thinking_token 事件
- **THEN** token 追加到管线消息的 thinkingContent
- **AND** 在管线 UI 的思考区域展示（可折叠，流式时展开）

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

系统 SHALL 在快速模式下处理搜索类 SSE 事件并设置助手消息的搜索状态属性，但当前实现中这些属性未在 UI 上渲染。

> 已知缺陷：SearchBanner 组件已定义但未引用（死代码），searchStatus/searchResults/searchQuery 被设置但用户不可见。此行为通过 delta 提案 add-search-banner 变更。

#### Scenario: 搜索开始设置状态

- **GIVEN** 快速对话 SSE 流进行中
- **WHEN** 收到 search_start 事件
- **THEN** 助手消息的 searchStatus 设为 'searching'，searchQuery 设为事件中的 query
- **AND** 搜索状态未在 UI 上渲染（SearchBanner 组件未使用）

#### Scenario: 搜索完成设置结果

- **GIVEN** 助手消息的 searchStatus 为 'searching'
- **WHEN** 收到 search_result 事件
- **THEN** searchStatus 设为 'done'，searchResults 设为事件中的结果列表
- **AND** 搜索结果未在 UI 上渲染（SearchBanner 组件未使用）

#### Scenario: 搜索失败设置错误状态

- **GIVEN** 助手消息的 searchStatus 为 'searching'
- **WHEN** 收到 search_error 事件
- **THEN** searchStatus 设为 'error'
- **AND** 错误状态未在 UI 上渲染

---

<!-- E. 对话流公共机制：两种模式共用的思考/工具/错误处理和 SSE 中断逻辑 -->

### Requirement: Conversation Stream Common Events

系统 SHALL 在深度模式的澄清阶段和快速模式中共用同一套对话流事件处理逻辑，包括 thinking、tool_call、chat 和 error 类事件。

#### Scenario: thinking_token 累积思考内容

- **GIVEN** 对话流进行中
- **WHEN** 收到 thinking_token 事件
- **THEN** token 追加到助手消息的 thinkingContent

#### Scenario: thinking_replace 替换思考内容

- **GIVEN** 对话流进行中，助手消息已有 thinkingContent
- **WHEN** 收到 thinking_replace 事件
- **THEN** thinkingContent 整体替换为事件中的 token（用于 DSML 清理等后处理）

#### Scenario: thinking_to_answer 将回答移至回答区

- **GIVEN** 对话流进行中，文本已作为 thinking_token 流式输出
- **WHEN** 收到 thinking_to_answer 事件
- **THEN** 将 thinkingContent 末尾与 answer 匹配的部分移至 chatResponse
- **AND** thinkingContent 保留剩余部分（思考轨迹），避免回答重复

#### Scenario: tool_call 记录到工具调用横幅

- **GIVEN** 对话流进行中
- **WHEN** 收到 tool_call 事件（非 run_deep_analysis）
- **THEN** 创建 ToolCallEntry（含图标、标签、参数摘要、done=false）追加到助手消息的 toolCalls 列表
- **AND** 工具调用与思考过程分离展示

#### Scenario: tool_result 附加到对应工具调用

- **GIVEN** 对话流进行中，助手消息已有工具调用记录
- **WHEN** 收到 tool_result 事件
- **THEN** 优先附加到同名且未完成的最近一次工具调用记录
- **AND** 若无同名未完成记录，回退到最近未完成的任意工具调用
- **AND** 若该记录已完成（已被 search_result/stock_resolved 等结构化事件先行附加），跳过避免重复
- **AND** 若无任何匹配记录且结果非空，新建一条仅含结果的工具调用记录

#### Scenario: chat_token 累积回答

- **GIVEN** 对话流进行中
- **WHEN** 收到 chat_token 事件
- **THEN** token 追加到助手消息的 chatResponse

#### Scenario: chat_done 结束流式

- **GIVEN** 对话流进行中，助手消息 streaming=true
- **WHEN** 收到 chat_done 事件
- **THEN** 助手消息 streaming 设为 false

#### Scenario: 对话流 error 事件

- **GIVEN** 对话流进行中
- **WHEN** 收到 error 事件
- **THEN** 助手消息 chatResponse 设为"❌ {message}"，streaming 设为 false

### Requirement: SSE Stream Abort Control

系统 SHALL 使用 AbortController 管理 SSE 流的生命周期，在切换会话、新建分析或删除当前会话时主动中断进行中的流。

#### Scenario: 切换会话时中断流

- **GIVEN** 深度分析或快速对话 SSE 流正在进行
- **WHEN** 用户选择另一个会话
- **THEN** 调用 abortStreaming() 中断当前 AbortController
- **AND** 中断后不显示错误消息（AbortError 静默退出）

#### Scenario: 新建分析时中断流

- **GIVEN** SSE 流正在进行
- **WHEN** 用户点击"新建分析"
- **THEN** 中断当前 SSE 流（静默退出）

#### Scenario: 删除当前会话时中断流

- **GIVEN** SSE 流正在进行，用户删除当前活动会话
- **WHEN** 删除操作执行
- **THEN** 中断当前 SSE 流（静默退出）

#### Scenario: 每轮请求新建 Controller

- **GIVEN** 上一轮 SSE 流已被中断或完成
- **WHEN** 发起新的 startAnalysis 或 quickChat 请求
- **THEN** 创建新的 AbortController 用于本轮流

#### Scenario: 非中断的连接错误显示错误消息

- **GIVEN** SSE 流正在进行
- **WHEN** 发生非 AbortError 的连接错误
- **THEN** 深度模式下添加 error 类型消息显示"连接错误: {message}"
- **AND** 快速模式下将助手消息更新为 error 类型

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

系统 SHALL 在报告消息中渲染报告头部、文件导出、财务图表、Markdown 正文、参考资料和免责声明。

#### Scenario: 流式报告显示生成指示器

- **GIVEN** 报告消息 streaming=true
- **THEN** 顶部显示"正在生成报告 · 流式输出中"指示器（脉冲动画）

#### Scenario: 报告头部展示

- **GIVEN** 报告消息 streaming=false
- **THEN** 显示股票名称（stockName）、"深度分析"标签、耗时信息
- **AND** 若 filePaths 中有 docx，显示 Word 导出按钮
- **AND** 若 filePaths 中有 pptx，显示 PPT 导出按钮

#### Scenario: 文件导出

- **GIVEN** 报告头部已渲染，存在 filePaths.docx 或 filePaths.pptx
- **WHEN** 用户点击导出按钮
- **THEN** 触发文件下载，URL 为 /api/files/{filename}

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

### Requirement: Thinking Banner Display

系统 SHALL 在助手消息中展示可折叠的思考过程横幅，流式时自动展开，完成后可手动折叠。

#### Scenario: 流式思考自动展开

- **GIVEN** 助手消息 streaming=true 且有 thinkingContent
- **THEN** 思考横幅自动展开，显示脉冲动画指示"正在思考"
- **AND** 内容区域自动滚动到底部

#### Scenario: 思考完成状态

- **GIVEN** 助手消息 streaming 从 true 变为 false
- **THEN** 脉冲动画停止，显示勾选图标
- **AND** 标题显示"已深度思考 · {N} 字"

#### Scenario: 手动折叠/展开

- **GIVEN** 思考横幅已渲染
- **WHEN** 用户点击横幅标题
- **THEN** 切换展开/折叠状态
- **AND** 折叠时内容区域高度为 0，展开时最大高度 240px

### Requirement: Tool Call Banner Display

系统 SHALL 在助手消息中将工具调用与思考过程分离展示，使用独立的可折叠横幅。

#### Scenario: 工具调用横幅展示

- **GIVEN** 助手消息包含 toolCalls（非空数组）
- **THEN** 在思考横幅上方渲染工具调用横幅
- **AND** 每个工具调用显示图标、标签、参数摘要
- **AND** 已完成的工具调用显示结果摘要
- **AND** 未完成的工具调用显示"执行中..."旋转动画

#### Scenario: 工具调用横幅状态

- **GIVEN** 助手消息 streaming=true 且有未完成工具调用
- **THEN** 横幅标题显示"调用工具中 · {N} 次"，脉冲动画
- **GIVEN** 助手消息 streaming=false
- **THEN** 横幅标题显示"已调用工具 · {N} 次"，勾选图标

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

系统 SHALL 根据消息类型（user/pipeline/report/chat/system/error）渲染不同样式的消息卡片。

#### Scenario: 用户消息右对齐

- **GIVEN** 消息类型为 'user'
- **THEN** 消息右对齐，使用品牌色背景

#### Scenario: 错误消息展示

- **GIVEN** 消息类型为 'error'
- **THEN** 消息左对齐，显示红色错误图标和错误文本

#### Scenario: 系统消息展示

- **GIVEN** 消息类型为 'system' 且内容不为 'typing'
- **THEN** 消息左对齐，显示机器人图标和成功勾选标记

#### Scenario: 助手消息展示

- **GIVEN** 消息类型为 'chat'
- **THEN** 消息左对齐，显示机器人图标
- **AND** 按顺序渲染：工具调用横幅、思考横幅、Markdown 回答
- **AND** 若 streaming=true 且无 chatResponse，显示"思考中..."旋转动画

### Requirement: Chat History Restore With Tool Calls

系统 SHALL 在加载已有会话时，从 chat_history 恢复助手消息的 thinking 内容和 tool_calls 记录。

#### Scenario: 恢复工具调用记录

- **GIVEN** 加载的会话 chat_history 中某条助手消息包含 tool_calls
- **WHEN** 构建助手消息
- **THEN** 将 tool_calls 映射为 ToolCallEntry 列表（含 name、args、result_text、done）
- **AND** 在助手消息中展示工具调用横幅

#### Scenario: 恢复思考内容

- **GIVEN** 加载的会话 chat_history 中某条助手消息包含 thinking 字段
- **WHEN** 构建助手消息
- **THEN** 将 thinking 内容设为助手消息的 thinkingContent
- **AND** 在助手消息中展示思考横幅（已完成状态）
