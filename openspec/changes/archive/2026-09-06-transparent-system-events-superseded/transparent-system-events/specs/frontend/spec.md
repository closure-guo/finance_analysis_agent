## ADDED Requirements

### Requirement: Rule-Triggered Event Handling

前端 SHALL 处理 chat 流的 `rule_triggered` / `rule_pre_search_start` / `rule_pre_search_complete` 事件，渲染为系统预处理指示 UI（区别于 ThinkingBanner），SHALL NOT 将规则事件写入 `agentTimeline` 的 `thinking` item 或 `tool_call` item。

#### Scenario: 收到 rule_triggered 显示系统预处理指示

- **GIVEN** chat 流进行中
- **WHEN** 收到 `rule_triggered` 事件
- **THEN** 前端 SHALL 显示系统预处理指示（如"系统预处理中"），区别于 ThinkingBanner 的"思考中"
- **AND** SHALL NOT 在 `agentTimeline` 创建 `thinking` 或 `tool_call` 类型 item

#### Scenario: 收到 rule_pre_search_start 显示搜索进行中

- **GIVEN** chat 流进行中，已收到 `rule_triggered`
- **WHEN** 收到 `rule_pre_search_start` 事件
- **THEN** 前端 SHALL 更新系统预处理指示为"规则预搜索中"，显示查询内容

#### Scenario: 收到 rule_pre_search_complete 显示搜索完成

- **GIVEN** chat 流进行中，规则预搜索进行中
- **WHEN** 收到 `rule_pre_search_complete` 事件
- **THEN** 前端 SHALL 更新系统预处理指示为"规则预搜索完成"，显示结果数量
- **AND** 后续 LLM 流式输出（thinking_token / chat_token）正常进入 `agentTimeline`，与规则预处理指示分离

### Requirement: System Note Event Handling

前端 SHALL 处理 analyze 流的 `system_note` 事件，渲染为系统提示 UI（区别于 ThinkingBanner），SHALL NOT 将 `system_note` 写入 `agentTimeline` 的 `thinking` item。

#### Scenario: 收到 node_progress 显示系统进度提示

- **GIVEN** analyze 流管线运行中
- **WHEN** 收到 `system_note` 事件且 `kind` 为 `node_progress`
- **THEN** 前端 SHALL 在对应管线节点阶段渲染系统进度提示（如"▶ 正在执行：技术分析…"）
- **AND** SHALL NOT 将该提示写入 `thinking` 类型 TimelineItem 或渲染为 ThinkingBanner

#### Scenario: 收到 node_summary 显示节点摘要

- **GIVEN** analyze 流管线运行中
- **WHEN** 收到 `system_note` 事件且 `kind` 为 `node_summary`
- **THEN** 前端 SHALL 在对应管线节点阶段渲染节点摘要提示
- **AND** SHALL NOT 将该摘要写入 `thinking` 类型 TimelineItem 或渲染为 ThinkingBanner

#### Scenario: system_note 与真实思考分离展示

- **GIVEN** analyze 流管线运行中，某节点阶段已有系统提示
- **WHEN** 该节点的 LLM 真实思考（`thinking_token`，来源 reasoning_content）到达
- **THEN** 真实思考 SHALL 进入 `thinking` 类型 TimelineItem 并渲染为 ThinkingBanner
- **AND** 系统提示（`system_note`）与真实思考（`thinking_token`）在 UI 上分层展示，互不混淆
