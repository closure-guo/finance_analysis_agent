# Delta for assertion-golden-set

## ADDED Requirements

### Requirement: 结算规则 golden 判例

golden 集 SHALL 含 `settlement_rule` 类型样本：给定交易决策（action/entry/stop/target/horizon）与行情序列，期望结算结果（止损触发/目标触发/超期/一字板等）与关键字段（return/exit_price/outcome），由人工裁决标注。gate SHALL 通过 `evaluate_decision` 复算并与人工裁决对照（唯一来源：结算逻辑仅 production 一处实现）。

#### Scenario: settle 判例对照

- **GIVEN** settlement_rule 样本（决策 + 行情 + 人工裁决）
- **WHEN** gate 运行
- **THEN** `evaluate_decision` 结果 SHALL 与样本 `expected.verdict` 一致
- **AND** 不一致即 FAIL（结算规则回归信号）