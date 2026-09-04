# agent-evaluation-suite Specification Delta

## ADDED Requirements

### Requirement: 在线 hosted evaluator

系统 SHALL 对生产 trace 启用 Langfuse managed evaluator（采样率配置化，默认 10%），维度对齐离线评测口径；自托管版本不支持时降级为轮询脚本方案。

#### Scenario: 采样打分

- **WHEN** 生产 trace 到达且命中采样
- **THEN** hosted evaluator 输出分数，与离线评分入同一分数命名空间并可按来源区分

### Requirement: 口径对齐验证

系统 SHALL 抽样比对 hosted 与离线 judge 对同一 trace 的打分差异，差异超阈值时告警。

#### Scenario: 口径漂移告警

- **WHEN** 同 trace 两套打分 MAE 超配置阈值
- **THEN** 报告标注口径漂移，提示统一裁判口径

### Requirement: 在线质量告警

hosted 均分跌破阈值 SHALL 触发告警（Langfuse webhook 或轮询脚本）；evaluator 模板作为 prompt 纳入版本管理与部署纪律。

#### Scenario: 均分告警

- **WHEN** 滑动窗口内 hosted 均分低于配置阈值
- **THEN** 产生告警并输出低分 trace 清单
