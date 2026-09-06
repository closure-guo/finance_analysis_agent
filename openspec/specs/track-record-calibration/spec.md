# track-record-calibration Specification

## Purpose
TBD - created by archiving change add-track-record-stage-c. Update Purpose after archive.
## Requirements
### Requirement: 置信度校准分桶

系统 SHALL 将已结算观点按 confidence 分桶（[0.5,0.6)...[0.9,1.0]），每桶输出 {桶中值, 实际命中率, 样本数}，样本不足桶如实返回样本数。

#### Scenario: 分桶输出

- **WHEN** 请求校准 API 且存在已结算观点
- **THEN** 返回各桶中值/实际命中率/样本数，neutral 观点按 0.5 命中处理（可配置剔除）

### Requirement: Brier Score

系统 SHALL 计算 Brier Score 作为概率校准汇总指标，并在校准页与校准曲线成对展示。

#### Scenario: 校准页展示

- **WHEN** 用户打开校准页
- **THEN** 呈现校准曲线（预期命中率 vs 实际命中率）与 Brier Score，样本不足时分桶如实标注

