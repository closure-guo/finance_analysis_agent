# track-record-versioning Specification Delta

## ADDED Requirements

### Requirement: Agent 版本登记

系统 SHALL 维护 `agents` 表（agent 标识/model_version/version_seq/retired_at），每次模型或策略升级产生新 version_seq，旧版本标记 retired_at。

#### Scenario: 版本升级封存

- **WHEN** 模型或策略升级并登记新版本
- **THEN** 旧版本 retired_at 落时间戳，之后产生的观点归属新 version_seq

### Requirement: 战绩分段不混算

统计与展示 SHALL 按 version_seq 分段封存，跨版本不混算（P6）；默认展示当前版本，历史版本可切换查看。

#### Scenario: 分段统计

- **WHEN** 查询胜率/指标且系统经历过版本升级
- **THEN** 结果按 version_seq 分段返回，汇总口径明确标注分段边界
