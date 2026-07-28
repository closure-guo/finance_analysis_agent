# Delta: frontend - add-search-banner

## MODIFIED Requirements

### Requirement: Quick Chat Search Events

系统 SHALL 在快速模式下处理搜索类 SSE 事件，并通过可折叠的搜索横幅向用户展示搜索状态和结果。

#### Scenario: 搜索开始显示搜索中状态

- **GIVEN** 快速对话 SSE 流进行中
- **WHEN** 收到 search_start 事件
- **THEN** 助手消息的 searchStatus 设为 'searching'，searchQuery 设为事件中的 query
- **AND** 在助手消息中渲染搜索横幅，显示"正在搜索：{query}"，脉冲动画指示搜索进行中

#### Scenario: 搜索完成展示结果

- **GIVEN** 助手消息的 searchStatus 为 'searching'
- **WHEN** 收到 search_result 事件
- **THEN** searchStatus 设为 'done'，searchResults 设为事件中的结果列表
- **AND** 搜索横幅显示"搜索了 N 个网页"（N 为结果数量）
- **AND** 搜索横幅可展开，展开后显示网页列表，每条包含序号、标题、摘要、域名、favicon

#### Scenario: 搜索失败显示错误状态

- **GIVEN** 助手消息的 searchStatus 为 'searching'
- **WHEN** 收到 search_error 事件
- **THEN** searchStatus 设为 'error'
- **AND** 搜索横幅显示搜索失败状态

#### Scenario: 搜索横幅可折叠

- **GIVEN** 搜索横幅已渲染（searchStatus 为 'done'）
- **WHEN** 用户点击搜索横幅标题
- **THEN** 切换展开/折叠状态
- **AND** 折叠时仅显示"搜索了 N 个网页"摘要行
- **AND** 展开时显示完整网页列表

## ADDED Requirements

### Requirement: Deep Mode Search Banner

系统 SHALL 在深度分析澄清阶段以独立搜索横幅展示搜索结果，与快速模式保持一致的 Kimi-style 交互。

#### Scenario: 澄清阶段搜索结果以搜索横幅展示

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 search_result 事件
- **THEN** 助手消息的 searchStatus 设为 'done'，searchResults 设为事件中的结果列表
- **AND** 在助手消息中渲染搜索横幅，显示"搜索了 N 个网页"
- **AND** 搜索横幅可展开查看网页列表（标题 + URL + 摘要 + favicon）
- **AND** 不再将搜索结果摘要附加到 ToolCallBanner

#### Scenario: 澄清阶段搜索开始显示搜索中状态

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 search_start 事件
- **THEN** 助手消息的 searchStatus 设为 'searching'，searchQuery 设为事件中的 query
- **AND** 在助手消息中渲染搜索横幅，显示"正在搜索：{query}"
