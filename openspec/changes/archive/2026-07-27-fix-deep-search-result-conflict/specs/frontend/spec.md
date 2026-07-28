# Delta: frontend - fix-deep-search-result-conflict

## MODIFIED Requirements

### Requirement: SSE Event: search_result (Deep Mode)

系统 SHALL 在深度分析澄清阶段收到 search_result 事件时，将搜索结果设置到助手消息的 searchStatus/searchResults 属性，由独立搜索横幅展示，与快速模式保持一致的 Kimi-style 交互。

#### Scenario: 搜索结果由独立搜索横幅展示

- **GIVEN** 深度分析 SSE 流进行中，pipelineMsgRef 为空（澄清阶段）
- **WHEN** 收到 search_result 事件
- **THEN** 助手消息的 searchStatus 设为 'done'，searchResults 设为事件中的结果列表
- **AND** 在助手消息中渲染搜索横幅，显示"搜索了 N 个网页"
- **AND** 搜索横幅可展开查看网页列表（标题 + URL + 摘要 + favicon）
- **AND** 不再将搜索结果摘要附加到 ToolCallBanner
