# track-record-integrity Specification

## Purpose
TBD - created by archiving change add-track-record-stage-c. Update Purpose after archive.
## Requirements
### Requirement: 快照完整性校验

系统 SHALL 对 `rationale_snapshot` 计算哈希，日批 `integrity-check` 任务逐条校验，发现篡改即告警并写审计日志。

#### Scenario: 篡改告警

- **WHEN** integrity-check 发现快照哈希与冻结字段重算值不一致
- **THEN** 记录审计日志（prediction_id/期望哈希/实际哈希/时间）并产生告警，不自动修复数据

### Requirement: 审计日志

对 predictions 表的一切状态变更 SHALL 写审计日志（操作/旧值/新值/来源任务/时间戳）。

#### Scenario: 状态变更留痕

- **WHEN** 观点状态由 open 变为 win/loss/superseded/unresolvable
- **THEN** 审计表追加一条含旧新状态与来源任务的记录

