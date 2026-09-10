# Delta for agent-prompt-contracts

## MODIFIED Requirements

### Requirement: 风控与审批评级量表

risk_judge、fund_manager 提示词 MUST 提供评级/决策选项的语义说明，指导在证据均衡或不足时如何取舍。fund_manager 提示词 MUST 额外定义审批理由的职责边界：approve 理由限定于风控结论一致性、论据矛盾处理与执行前提；MUST NOT 对标的作方向性投资判断（如「适合长期价值投资」——该类判断属研究层，FM 无分析师报告输入而无依据）。

#### Scenario: Risk Judge 输出评级量表决策

- **WHEN** 加载 risk_judge 提示词
- **THEN** 模板中包含 buy/sell/hold/watch 的语义与取舍指导（如证据均衡时倾向 hold/watch）

#### Scenario: Fund Manager 审批决策语义

- **WHEN** 加载 fund_manager 提示词
- **THEN** 模板中包含 approve/reject/return 三种决策的适用语义说明
- **AND** 模板中包含 approve 时输出 action（操作定性，枚举同交易方案）与 confidence（0-1）的格式要求及语义说明（action 是对最终方案的操作定性，非对裁决的赞成/否决票）

#### Scenario: Fund Manager 审批理由职责边界

- **WHEN** 加载 fund_manager 提示词
- **THEN** 模板中包含 approve/return/reject 理由的职责边界条款（限定于风控结论一致性、论据矛盾处理、执行前提）
- **AND** 模板中包含禁止方向性投资判断的反例表述（如不得出现「适合长期价值投资/买入」类背书）
