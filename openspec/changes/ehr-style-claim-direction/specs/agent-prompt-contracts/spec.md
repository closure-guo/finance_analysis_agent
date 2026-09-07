# agent-prompt-contracts Delta

## ADDED Requirements

### Requirement: 分析师 claim 方向申报纪律

数值型与计算型 claim 的分析师 prompt（fundamental/technical/sentiment 及辩论者）SHALL 要求：登记 claim 时必填 `direction` 字段（`positive`/`negative`/`flat`），方向语义为「正文表述方向对应真值符号的修饰」——正文写「下滑 10.05%」而真值为 -10.05 时 SHALL 申报 `stated_value=10.05, direction="negative"`。prompt SHALL 提供与 field_ref ↔ metric_name 同级的 direction 申报示例。prompt 变更后 SHALL 经 `scripts/deploy_prompts.py` 发布方可进入 eval 门禁（prompt-deploy-consistency 契约不变）。

#### Scenario: prompt 含方向申报示例

- **WHEN** 审查任一分析师 prompt 的 claim 登记章节
- **THEN** SHALL 存在 direction 必填说明与「下滑 X% → stated_value=X, direction=negative」样例

#### Scenario: prompt 发布一致性

- **WHEN** prompt 修改合入后未执行 deploy_prompts.py
- **THEN** eval 门禁 SHALL 拒绝运行（沿用现有 prompt-deploy-consistency 门禁行为）
