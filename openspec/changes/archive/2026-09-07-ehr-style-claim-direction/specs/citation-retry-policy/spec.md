# citation-retry-policy Delta

## ADDED Requirements

### Requirement: 定向重试反馈携带 direction 申报提示

校验失败触发的定向重试反馈（value_mismatch / direction_mismatch 桶）与 coverage 打回（coverage_gap）SHALL 在反馈条目中携带 direction 申报提示：未申报 direction 的覆盖缺口 SHALL 提示「补登记时同步申报 direction」；direction_mismatch 的重试反馈 SHALL 携带校验器解析的真值符号，分析师 SHALL 据此修正 stated_value 与 direction 的组合而非仅改数值。

#### Scenario: direction_mismatch 重试反馈含真值符号

- **WHEN** claim 因 direction_mismatch 判 FAIL 进入定向重试
- **THEN** 反馈条目 SHALL 包含 ground_truth 数值及其符号，与 direction 申报格式示例

#### Scenario: 覆盖缺口补登记携带 direction 提示

- **WHEN** coverage 打回生成 coverage_gap 反馈条目
- **THEN** 条目 SHALL 包含 direction 申报提示字段，提示分析师补 claim 时一并申报方向
