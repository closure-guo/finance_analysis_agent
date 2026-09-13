# Proposal: add-latency-cost-regression

## Why

评估体系目前只管「答得好不好」，不管「答得多贵多慢」。深度模式一次分析串行 10+ 个 LLM 调用，token 成本与时延是真实运营约束；prompt 越写越长、模型越换越贵却无任何回归护栏。improve-analyst-throughput 等历史优化也没有持续度量能守住成果。

## What Changes

- 度量采集：从 Langfuse trace 聚合每次分析的 {端到端时延, 节点时延分解, token 用量, 折算成本}（quick/deep 分开统计）
- 基线档案：`docs/evals/` 落性能基线（类似 v3 delta 归档），每次评测对比基线
- 回归门禁：时延/成本超基线 X% 即告警或失败（阈值可配置）；作为评测报告的固定一节
- 趋势追踪：nightly 运行沉淀时序数据，识别缓慢劣化（单次不超阈值但趋势向上）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增性能回归维度（度量采集、基线对比、门禁阈值、趋势归档）

## Impact

- 依赖：Langfuse usage/trace 字段（既有，无需新埋点）
- 纯评测侧增量，零生产链路改动
- 注意：成本折算依赖模型单价表，需随供应商调价维护（配置化，不硬编码）
