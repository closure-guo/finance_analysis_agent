## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: Pipeline Thinking Display

系统 SHALL 在管线 UI 中按 agent 阶段分组展示思考过程，每个 agent 阶段内按时间序列排列该 agent 的 timeline items（思考/搜索/工具调用横幅），与管线进度区域分离。

#### Scenario: 管线运行期间思考流式追加到对应阶段

- **GIVEN** 管线 UI 已渲染，pipelineMsgRef 不为空
- **WHEN** 收到 `thinking_token` 事件（含 `node` 字段标识所属 agent）
- **THEN** 将该 token 累加到对应 agent 阶段的 timeline 末尾 thinking item（或新建 thinking item）
- **AND** 在该 agent 阶段区域内渲染 ThinkingBanner（可折叠，流式时展开）

#### Scenario: 管线阶段分组展示

- **GIVEN** 管线 UI 已渲染
- **WHEN** 渲染管线消息
- **THEN** 保留阶段进度条
- **AND** 每个 agent 阶段的 timeline items 归在该阶段下，阶段间用角色名标题分隔（如"多头分析师"、"空头分析师"、"Trader"）
- **AND** 角色名标题为纯文本，非折叠框
- **AND** 阶段内按时间序列排列该 agent 的思考/搜索/工具调用横幅
- **AND** 当前活动阶段的横幅展开，已完成阶段的横幅折叠

### Requirement: Conversation Stream Common Events

系统 SHALL 在深度模式的澄清阶段和快速模式中共用同一套对话流事件处理逻辑，将 thinking、search、tool_call、chat 类事件写入 `agentTimeline` 数组（按事件时序）和 `chatResponse`（回答正文）。

#### Scenario: thinking_token 累积到 timeline 末尾 thinking item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `thinking_token` 事件
- **THEN** 若 `agentTimeline` 末尾是 `thinking` 类型 item，将 token 累加到该 item 的 `content`
- **AND** 否则新建 `{type:'thinking', content: token}` item 追加到 `agentTimeline`

#### Scenario: thinking_replace 替换 timeline 末尾 thinking item 内容

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是 `thinking` 类型 item
- **WHEN** 收到 `thinking_replace` 事件
- **THEN** 该 item 的 `content` 整体替换为事件中的 token（用于 DSML 清理等后处理）

#### Scenario: thinking_to_answer 将回答移至 chatResponse

- **GIVEN** 对话流进行中，文本已作为 thinking_token 流式输出到 timeline 末尾 thinking item
- **WHEN** 收到 `thinking_to_answer` 事件
- **THEN** 将该 thinking item `content` 末尾与 answer 匹配的部分移至 `chatResponse`
- **AND** 该 thinking item `content` 保留剩余部分（思考轨迹），避免回答重复

#### Scenario: tool_call 新建 tool_call item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `tool_call` 事件（非 run_deep_analysis，非搜索类工具）
- **THEN** 新建 `{type:'tool_call', name, args, done:false}` item 追加到 `agentTimeline`

#### Scenario: tool_result 更新对应 tool_call item

- **GIVEN** 对话流进行中，`agentTimeline` 已有 tool_call item
- **WHEN** 收到 `tool_result` 事件
- **THEN** 优先更新同名且 `done=false` 的最近一次 tool_call item（设 `result` 和 `done=true`）
- **AND** 若无同名未完成记录，回退到最近未完成的任意 tool_call item
- **AND** 若无任何匹配记录且结果非空，新建一条仅含结果的 tool_call item

#### Scenario: search 事件生成 search item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `search_start` / `search_result` / `search_error` 事件
- **THEN** 新建或更新 `search` 类型 TimelineItem（见 Agent Timeline Display 需求）
- **AND** 搜索类工具不生成 tool_call item

#### Scenario: chat_token 累积回答

- **GIVEN** 对话流进行中
- **WHEN** 收到 `chat_token` 事件
- **THEN** token 追加到助手消息的 `chatResponse`

#### Scenario: chat_done 结束流式

- **GIVEN** 对话流进行中，助手消息 streaming=true
- **WHEN** 收到 `chat_done` 事件
- **THEN** 助手消息 streaming 设为 false
- **AND** 所有 thinking item 用 `extractThinkingTitle` 提取标题写入 `title` 字段

#### Scenario: 对话流 error 事件

- **GIVEN** 对话流进行中
- **WHEN** 收到 `error` 事件
- **THEN** 助手消息 `chatResponse` 设为"❌ {message}"，streaming 设为 false

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

系统 SHALL 在加载已有会话时，从 `chat_history` 恢复助手消息的 `agentTimeline`（重建思考与工具调用的时序）。

#### Scenario: 恢复 agentTimeline

- **GIVEN** 加载的会话 `chat_history` 中某条助手消息包含 `thinking` 和 `tool_calls`
- **WHEN** 构建助手消息
- **THEN** 从 `thinking`（合并字符串）构建 `{type:'thinking', content}` item
- **AND** 从 `tool_calls`（数组）按序构建 `{type:'tool_call', name, args, result, done}` items
- **AND** 按"思考在前、工具调用在后"的顺序排列到 `agentTimeline`
- **AND** 每个 thinking item 用 `extractThinkingTitle` 提取标题写入 `title`

#### Scenario: 恢复搜索记录

- **GIVEN** 加载的会话 `chat_history` 中某条助手消息包含搜索相关记录（若后端存储）
- **WHEN** 构建助手消息
- **THEN** 构建 `{type:'search', query, results, status:'done'}` item 插入 `agentTimeline` 对应位置
- **AND** 若后端未存储搜索时序，按"思考 -> 搜索 -> 工具调用"的近似顺序排列

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
- **WHEN** 收到 thinking_token / thinking_replace / thinking_to_answer 事件
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
