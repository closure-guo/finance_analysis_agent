# Proposal: declare-technical-context-array-order

## Why

契约修复冒烟验证（incident 022，2026-08-30）发现第四类契约疾病：技术指标 context 只声明了「各序列为最近 60 期 + 负索引约定（-1=最新一期）」，但**未声明序列数组内部顺序**。state 的 technical 序列为时间正序（旧→新，`fetch_kline` 显式 `sort_values("日期")` 升序，末尾=最新），LLM 却按主流行情展示习惯（最新在前）把**窗口首元素**（60 个交易日前）误读为「最新」——中际旭创 300308 深跑 13 条技术 claim 全部期次错位 FAIL（如 stated MA5=1211.36，真实最新=858.32），并据此编造出方向相反的多头排列叙事。校验器的负索引解析本身正确，无契约修改，问题纯在 context/prompt 对数组方向的缺省歧义。

## What Changes

- 技术指标 context 的序列说明 SHALL 明示数组顺序：「时间正序（旧→新），列表**末尾**为最新一期」；
- 技术分析师反幻觉规则 SHALL 增加「引用 -N 前先核对所在序列**尾部**（-1=最后一个元素）」的自证约束；
- 校验器 `citation.py` **零改动**（负索引语义已正确，见 Incident 022 归因）。

## Capabilities

- **Modified Capabilities**: `citation-verification`（扩展「序列引用负索引语义」需求：补充数组方向声明与自证场景）

## Impact

- `src/finance_agent/nodes/analysts.py`：`_build_technical_context` 的序列注记文本 + 技术分析师 prompt 反幻觉规则（`src/finance_agent/prompts/technical_analyst.md`，改后须 `deploy_prompts.py` 发布）；
- E2E：无交互层变更，不适用前端门禁；
- 回归对照组：incident 022 的中际旭创类样本（stated=窗口首元素 vs gt=尾部）在修复后应 FAIL→PASS 翻转。