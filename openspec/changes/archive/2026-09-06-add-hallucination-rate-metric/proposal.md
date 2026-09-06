# Proposal: add-hallucination-rate-metric

## Why

引用体系（citation v3 语义覆盖）保证了「引用的句子有出处」，但不保证「数字和事实是对的」——agent 可能引用真实来源却写错数值，或陈述无来源的事实性 claim。金融场景幻觉代价高，目前无专门度量。

## What Changes

- 事实抽取：从最终报告抽取可验证 claim（数值型：价格/涨跌幅/财务指标；事实型：事件/日期/主体）
- 校验回路：claim 对照证据源（K 线/财报 API 真实数据 + 检索内容），判定 supported / contradicted / unverifiable
- 指标：`hallucination_rate` = contradicted / 可验证 claim 总数；unverifiable 单列不进分子（避免惩罚合理推断）
- 门禁：幻觉率上限纳入评测门禁；nightly @live 追踪趋势

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增幻觉率指标（claim 抽取、证据校验、门禁阈值）

## Impact

- 依赖：数据源 API（akshare 既有封装）作为校验基准；citation 体系的 claim 定位可复用
- 成本：校验需要额外 LLM 调用（claim 抽取）——只在评测链路跑，不进生产链路
- 与 add-toolcall-evaluation 共用工具返回内容作为证据源
