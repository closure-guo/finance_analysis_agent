# Proposal: update-report-data-disclosure

## Why

第七轮人工评审（2026-10-05）记录两处表述完整性瑕疵（issue #233）：① 国庆假期生成的报告使用 9-30 节前最后交易日行情，行为正确但正文无声明，读者无法从成稿判断数据新鲜度；② sentiment 成稿「科创板主力资金转为净流入（10.31亿元）」——已查实数字来自 news_list 新闻源、系板块口径而非个股，数字真实可溯但出现在个股报告里易被误读为个股资金流。

## What Changes

- 报告头部新增「行情数据截止」声明行：取 `state["kline"]` 最后交易日，代码确定性拼装；kline 缺失时省略该行（诚实标注模式，不伪造日期）
- sentiment 分析师提示词补口径显式化纪律：引用板块级/市场级资金与情绪数据时 SHALL 显式标注「板块口径」（及来源形态），MUST NOT 与个股数据混写

## Capabilities

- **Modified Capabilities**: `report-decision-rendering`（新增数据新鲜度披露 Requirement）、`agent-prompt-contracts`（板块口径显式化并入）

## Impact

- `src/finance_agent/nodes/report.py` 头部拼装一处
- `src/finance_agent/prompts/sentiment_analyst.md` 一条纪律 + `tests/test_prompt_contracts.py` 同步
- prompt 变更须 `uv run python scripts/deploy_prompts.py` 发布（eval 门禁依赖）
- 关联 #190（口径披露补映射行先例）、#233
