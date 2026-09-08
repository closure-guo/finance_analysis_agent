# agent-evaluation-suite Specification Delta

## ADDED Requirements

### Requirement: 性能度量采集

评估链路 SHALL 从 Langfuse trace 聚合每次分析的端到端时延、节点时延分解、token 用量与折算成本，quick/deep 分开统计；模型单价表配置化。

#### Scenario: 度量聚合

- **WHEN** 评测运行完成
- **THEN** 报告含性能一节：两种模式的时延/token/成本汇总与节点分解

### Requirement: 基线对比与回归门禁

系统 SHALL 在 docs/evals/ 维护性能基线档案，评测对比基线；时延或成本超基线配置百分比即告警或失败。

#### Scenario: 回归拦截

- **WHEN** 端到端时延或成本超基线阈值
- **THEN** 门禁按配置告警或失败，报告标注退化维度

### Requirement: 趋势追踪

nightly 运行 SHALL 沉淀性能时序数据，识别单次不超阈值但趋势向上的缓慢劣化。

#### Scenario: 趋势识别

- **WHEN** 连续 N 轮（配置化）指标单调劣化且累计幅度超阈值
- **THEN** 报告标注趋势告警，即使单轮未触发门禁
