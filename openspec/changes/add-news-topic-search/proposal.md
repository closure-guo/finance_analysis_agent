# Proposal: add-news-topic-search

## Why

实测（2026-09-12，2 个代表性 query 各拉满 20 条）显示「最新消息」类 query 用 general 检索召回的全是行情页/导航页（18 条中 0 条真实新闻），而 Tavily 原生支持 `topic='news'`。新闻意图的 query 切换 news 通道是对搜索信息量最对症的改进（比提高结果条数有效，见同日权衡记录）。

## What Changes

- `tavily_search` 增加 topic 自动判别：query 命中新闻意图词表（新闻/最新/消息/动态/近期…）时自动以 `topic='news'` 调用 Tavily；显式传入 topic 参数时以显式值为准；未命中保持 general（现状）
- 纯函数 `detect_search_topic` 承载词表判别（可测、词表可演进）
- 不改变结果条数（max_results 维持 5）、不改变批量搜索去重逻辑

## Capabilities

- **New Capabilities**: web-search（搜索行为契约首次入主规范库）
- **Modified Capabilities**: 无

## Impact

- `src/finance_agent/web_search.py`：tavily_search 签名加 topic 可选参数 + 自动判别
- 调用方（agent_factory / react_agent）零改动（判别在 tavily_search 内部单点收口）
- 测试：tests/test_web_search_tool.py 增补判别与透传用例
