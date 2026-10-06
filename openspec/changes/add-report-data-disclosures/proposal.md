# Proposal: add-report-data-disclosures

## Why

第七轮人工评审（2026-10-05，issue #233）记录两处表述完整性瑕疵：

1. 舆情成稿出现「科创板主力资金转为净流入（10.31 亿元）」——数字真实、来源可溯
   （news_list 新闻源），但「科创板」是板块口径而非 688072 个股口径，出现在个股报告
   里易被读者误读为个股资金流。
2. 国庆休市期间（10-01~10-08）生成的报告使用 9-30 节前最后交易日行情，行为正确，
   但正文无任何声明，读者无法从成稿判断行情数据新鲜度。

## What Changes

- sentiment_analyst 提示词增补「外部口径显式化」约束：引用板块/行业/全市场口径的
  市场数据时 MUST 显式标注口径主体与来源属性（新闻源口径），防止个股报告语境下的
  口径误读。
- 报告头部元信息行确定性渲染「行情数据截止 YYYY-MM-DD」（取输入 kline 最后交易日，
  渲染层直读 state 不经 LLM；kline 缺失/为空/不可解析时省略，零回归）。

## Capabilities

- **Modified Capabilities**:
  - `agent-prompt-contracts`（ADDED requirement：舆情分析师外部口径显式化）
  - `agent-node-contracts`（ADDED requirement：报告头部行情数据截止声明）

## Impact

- `src/finance_agent/prompts/sentiment_analyst.md`（权威源，需 deploy_prompts 发布）
- `src/finance_agent/nodes/report.py`（generate_report 头部渲染）
- 测试：`tests/test_prompt_contracts.py`、`tests/nodes/test_report.py`
- 纯后端渲染与 prompt 约束，不涉及前端 UI / SSE / 会话切换 / 状态流转，
  不适用 E2E 门禁（§3.5）。
