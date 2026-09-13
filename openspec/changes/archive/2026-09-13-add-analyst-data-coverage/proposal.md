# Proposal: add-analyst-data-coverage

## Why

信息获取层实测盘点（2026-09-12）：管线缺公告原文、券商研报、限售解禁/大宗交易三类 A 股核心信息面。公告是 claim 密度最高的信源；研报评级/目标价是 trader 决策的直接市场参照；解禁/大宗是事件性压力源（遗漏会导致误判支撑）。电话会议经评估不做（无稳定公开数据源，业绩会报道已由新闻间接覆盖）。

## What Changes

- 新增 4 个数据获取器：公告（巨潮 cninfo）、券商研报（东财）、限售解禁（东财）、大宗交易（东财，按日期区间拉取后按个股过滤）
- state 新键：announcements / research_reports / share_unlock / block_trades，走既有并行装配与缓存（TTL 3600）
- 基本面分析师 prompt 消费公告+研报（研报观点 SHALL 附防锚定条款：评级/目标价是卖方观点，不得作为结论依据）；舆情分析师 prompt 消费解禁+大宗（事件面）
- citation 门禁：四个新信源的标题进文本 claim 回声匹配源集合（与 news_list/key_events 同路径）
- 舆情 tavily 兜底不在本 delta（单独小 delta）

## Capabilities

- **New Capabilities**: analyst-data-sources
- **Modified Capabilities**: 无（citation 回声源扩展走新 capability 内 requirement）

## Impact

- `src/finance_agent/data/akshare_client.py`（4 fetcher）、`nodes/fetch.py`（装配+缓存）、`state.py`（4 键）
- `nodes/analysts.py` 的基本面/舆情 prompt 上下文（经 prompts/*.md——prompt 变更须 deploy_prompts）
- `citation.py` 回声匹配源集合
- 断网/接口失败时各源静默降级为空列表（与 fetch_news 同语义），分析师 prompt 已有空态分支
