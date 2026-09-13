# web-search Specification

## Purpose
TBD - created by archiving change add-news-topic-search. Update Purpose after archive.
## Requirements
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

### Requirement: 多角度检索引导写入工具描述

web_search 与 batch_web_search 的 LLM 可见描述 SHALL 包含基于实测的检索策略引导：web_search SHALL 引导新闻/舆情等多面话题改用 batch_web_search 从多个角度发问；batch_web_search SHALL 建议 2-3 个不同角度（角度选择优先于数量），并注明个股行情/报价类关键词召回的多为行情页、不建议作为搜索角度。

#### Scenario: 描述引导契约

- GIVEN Agent 构建工具 schema（docstring 即 LLM 可见描述）
- WHEN 加载 web_search 与 batch_web_search 工具
- THEN web_search 描述 SHALL 含 batch_web_search 引导与行情类查询警示
- AND batch_web_search 描述 SHALL 含「2-3 个不同角度」建议与行情类角度警示

#### Scenario: 已知边界

- react_agent 路径的工具集（REACT_TOOLS）不含 batch_web_search，其描述不做 batch 引导（避免引导到不存在的工具）——后续如需覆盖 react 路径，须先扩展其工具集

