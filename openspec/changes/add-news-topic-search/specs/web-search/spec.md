# Delta for web-search

## ADDED Requirements

### Requirement: 新闻意图 query 自动切换 news 检索通道

web 搜索 SHALL 对 query 做新闻意图判别：命中新闻意图词表（如「新闻/最新/消息/动态/近期/今天/本周」等时间敏感词）的 query SHALL 以 Tavily `topic='news'` 检索；未命中的 query SHALL 保持 general 检索（现状不变）。调用方显式传入 topic 时 SHALL 以显式值为准，不做覆盖。

#### Scenario: 新闻意图 query 走 news 通道

- GIVEN 用户或 Agent 发起搜索 query「贵州茅台 最新消息」
- WHEN 执行 Tavily 检索
- THEN 系统 SHALL 以 topic='news' 调用 Tavily API
- AND 结果条数上限 SHALL 与 general 检索一致（max_results 不变）

#### Scenario: 非新闻 query 保持 general 通道

- GIVEN 搜索 query「贵州茅台 股价」
- WHEN 执行 Tavily 检索
- THEN 系统 SHALL 以 general 通道检索（与现状一致）

#### Scenario: 显式 topic 优先于自动判别

- GIVEN 调用方显式传入 topic='general' 且 query 含新闻意图词
- WHEN 执行 Tavily 检索
- THEN 系统 SHALL 使用显式传入的 topic，SHALL NOT 被自动判别覆盖
