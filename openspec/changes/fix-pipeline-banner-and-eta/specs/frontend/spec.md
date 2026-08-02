# Delta Spec: frontend

## MODIFIED Requirements

### Requirement: Pipeline Progress Display

系统 SHALL 在深度分析期间展示 6 阶段管线进度，每阶段映射到后端 LangGraph 节点。无论 fast path 还是 agent 路径，后端 SHALL 为每个图节点发送 `node_start` 与 `node_complete` 事件对。

#### Scenario: 管线 6 阶段定义

- **GIVEN** 深度分析管线 UI 已渲染
- **THEN** 展示 6 个阶段节点：PREP、Layer I、Layer II、Trader、Risk、Fund Manager
- **AND** 每个阶段映射到后端节点：check_cache(PREP)、technical_analyst(Layer I)、bull_r1(Layer II)、trader(Trader)、aggressive_r1(Risk)、fund_manager(Fund Manager)

#### Scenario: 节点开始时更新阶段状态

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 node_start 事件
- **THEN** 对应阶段状态更新为 'running'，显示当前节点 ID 和层级描述
- **AND** 管线消息内容更新为"{layer}: {desc}..."
- **AND** currentNode 更新为该节点 ID，用于驱动该节点思考横幅的活动态

#### Scenario: agent 路径发送 node_start

- **GIVEN** 深度分析经 agent 路径（harness ReAct）执行 run_deep_analysis 流式工具
- **WHEN** graph.stream 迭代中某图节点的 updates chunk 首次出现
- **THEN** 后端 SHALL 先发送该节点的 node_start 事件（携带 node、layer、desc），再发送 node_complete
- **AND** 同一节点重复出现时不重复发送 node_start

#### Scenario: 节点完成时更新进度

- **GIVEN** 管线 UI 已渲染
- **WHEN** 收到 node_complete 事件
- **THEN** 对应阶段状态更新为 'completed'
- **AND** 进度条更新为事件中的 progress 值
- **AND** 节点输出记录到 nodeOutputs
- **AND** 管线消息内容更新为"{layer}: {desc} ✓"
- **AND** currentNode 清空或切换到下一 running 节点

#### Scenario: 阶段状态推断

- **GIVEN** 管线 UI 已渲染，某阶段的全部子节点均已 completed
- **THEN** 该阶段状态为 'completed'
- **WHEN** 某阶段有子节点正在 running
- **THEN** 该阶段状态为 'running'
- **AND** 其余阶段状态为 'pending'

#### Scenario: Layer II 子节点进展可见

- **GIVEN** 管线进入 Layer II（bull_r1/bear_r1/bull_r2/bear_r2/research_manager 串行执行）
- **WHEN** 各子节点依次 node_start / node_complete
- **THEN** 管线消息内容逐节点更新（如"Layer II: 看多辩论 R1..."→"Layer II: 看多辩论 R1 ✓"→"Layer II: 看空辩论 R1..."）
- **AND** 当前 running 子节点显示已运行时长（由 node_start 时间戳驱动，每秒刷新）

#### Scenario: Layer I 分析师卡片展示

- **GIVEN** 管线进入 Layer I 阶段（check_cache 完成或 technical_analyst 运行中/完成）
- **THEN** 展示 4 个分析师卡片（基本面/技术面/宏观/舆情）
- **WHEN** technical_analyst 节点未完成
- **THEN** 4 个卡片状态均为 'running' 或 'pending'，摘要为"分析中..."或"等待中..."
- **WHEN** technical_analyst 节点完成
- **THEN** 4 个卡片状态均为 'completed'，摘要更新为"XX分析完成"

### Requirement: Pipeline Thinking Display

系统 SHALL 在管线 UI 中按 agent 阶段分组展示思考过程，每个 agent 阶段内按时间序列排列该 agent 的 timeline items（思考/搜索/工具调用横幅），与管线进度区域分离。思考横幅 SHALL 在对应节点完成时显式折叠为完成态。

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

#### Scenario: 节点完成时思考横幅显式折叠

- **GIVEN** 管线运行中，节点 N 的 thinking item 处于流式活动态
- **WHEN** 收到节点 N 的 node_complete 事件
- **THEN** 节点 N timeline 末尾的 thinking item 置为完成态（done=true）
- **AND** 该 ThinkingBanner 折叠为"思考已完成"样式，不再依赖 currentNode 位置推断

#### Scenario: 下一节点思考开始时上一节点横幅收口

- **GIVEN** 管线运行中，节点 A 的 thinking item 因故未收到 node_complete 收口
- **WHEN** 收到节点 B（B ≠ A）的 thinking_token 事件
- **THEN** 节点 A 末尾未完成的 thinking item 置为完成态并折叠

### Requirement: Conversation Stream Common Events

系统 SHALL 在深度模式的澄清阶段和快速模式中共用同一套对话流事件处理逻辑，将 thinking、search、tool_call、chat 类事件写入 `agentTimeline` 数组（按事件时序）和 `chatResponse`（回答正文）。思考横幅 SHALL 在思考结束（出现后续事件）时显式置为完成态并自动折叠。

#### Scenario: thinking_token 累积到 timeline 末尾 thinking item

- **GIVEN** 对话流进行中
- **WHEN** 收到 `thinking_token` 事件
- **THEN** 若 `agentTimeline` 末尾是 `thinking` 类型 item，将 token 累加到该 item 的 `content`
- **AND** 否则新建 `{type:'thinking', content: token, done:false}` item 追加到 `agentTimeline`

#### Scenario: thinking_replace 替换 timeline 末尾 thinking item 内容

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是 `thinking` 类型 item
- **WHEN** 收到 `thinking_replace` 事件
- **THEN** 该 item 的 `content` 整体替换为事件中的 token（用于 DSML 清理等后处理）

#### Scenario: thinking_to_answer 将回答移至 chatResponse

- **GIVEN** 对话流进行中，文本已作为 thinking_token 流式输出到 timeline 末尾 thinking item
- **WHEN** 收到 `thinking_to_answer` 事件
- **THEN** 将该 thinking item `content` 末尾与 answer 匹配的部分移至 `chatResponse`
- **AND** 该 thinking item `content` 保留剩余部分（思考轨迹），避免回答重复
- **AND** 该 thinking item 置为完成态（done=true）并折叠

#### Scenario: 思考后接工具调用时思考横幅折叠

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是未完成（done=false）的 thinking item
- **WHEN** 收到 `tool_call` 事件
- **THEN** 该 thinking item 置为完成态（done=true）
- **AND** ThinkingBanner 从"思考中"切换为"思考已完成"并自动折叠

#### Scenario: 思考后接回答 token 时思考横幅折叠

- **GIVEN** 对话流进行中，`agentTimeline` 末尾是未完成（done=false）的 thinking item
- **WHEN** 收到首个 `chat_token` 事件
- **THEN** 该 thinking item 置为完成态（done=true）并自动折叠

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
- **AND** 所有 thinking item 置为完成态（done=true），用 `extractThinkingTitle` 提取标题写入 `title` 字段

#### Scenario: 对话流 error 事件

- **GIVEN** 对话流进行中
- **WHEN** 收到 `error` 事件
- **THEN** 助手消息 `chatResponse` 设为"❌ {message}"，streaming 设为 false
- **AND** 所有未完成 thinking item 置为完成态（done=true）

## ADDED Requirements

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
