# Delta Spec: frontend

## MODIFIED Requirements

### Requirement: Pipeline Progress Display

系统 SHALL 在深度分析期间以**分层时间轴**展示管线进度：顶层为 6 个 layer 节点（PREP / Layer I / Layer II / Trader / Risk / Fund），每个 layer 可展开显示其子节点列表。每个 layer 与子节点 SHALL 显示状态图标（等待/运行/完成/失败）与耗时，当前运行的子节点 SHALL 显示已运行时长并被高亮。无论 fast path 还是 agent 路径，后端 SHALL 为每个图节点发送 `node_start` 与 `node_complete` 事件对。

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
