# agent-evaluation-suite Specification Delta

## ADDED Requirements

### Requirement: 人工标注工具

系统 SHALL 提供标注脚本：从 Langfuse 抽样 trace 导出评判表（维度 × 人工 1-5 分），支持多轮标注与仲裁，样本集落 tests/fixtures/。

#### Scenario: 抽样导出

- **WHEN** 运行标注导出脚本并指定抽样规模与模式（quick/deep）
- **THEN** 生成含 trace 摘要与空人工评分列的标注表

### Requirement: judge-人工一致性指标

系统 SHALL 计算 judge 分 vs 人工分的 Spearman 相关、MAE、方向一致率，输出校准报告至 reports/。

#### Scenario: 一致性报告

- **WHEN** 标注完成并运行一致性计算
- **THEN** 报告给出三项指标，低于配置阈值时标记需修订 judge prompt

### Requirement: 校准触发与归档

judge prompt 变更后 SHALL 必跑一致性校准；校准结论归档至 docs/evals/。

#### Scenario: 变更后强制校准

- **WHEN** judge prompt 经部署管线发布新版本
- **THEN** 下一轮评测强制附带一致性校准，结论归档
