# Delta for agent-prompt-contracts

## MODIFIED Requirements

### Requirement: Trader 决策语义契约

trader 提示词 MUST 定义 action 各档位的语义与 position_size 档位含义，并为 confidence 提供分档锚点。sell 档位语义 MUST 按 `sell_type` 分型表述（update-sell-action-typing，issue #188）：**exit**（持有者减仓/退出敞口——MUST 申报 `exit_schedule` 减仓节奏，MUST NOT 套用建仓价位模板，重新介入条件写入 `reeval_triggers`）与 **short**（做空建仓——沿用 entry/stop/target 必填模板）。risk_judge 提示词 MUST 含同款 sell_type 语义与申报要求（终稿层与 Trader 同契约，避免两层语义漂移）。

#### Scenario: Trader 输出带语义的决策

- **WHEN** 加载 trader 提示词
- **THEN** 模板中包含 action（buy/sell/hold/watch）各档位的行为语义描述
- **AND** 模板中包含 position_size 档位定义（如 light/moderate/heavy 对应仓位区间）
- **AND** 模板中包含 confidence 分档语义（如 0.7+ 高置信、0.4-0.7 中等、<0.4 低置信）

#### Scenario: sell 分型语义与申报要求

- **WHEN** 加载 trader 或 risk_judge 提示词
- **THEN** 模板中包含 sell_type 双型语义（exit=持有者减仓/退出敞口；short=做空建仓）与对应参数要求（exit 申报 exit_schedule、short 申报 entry/stop/target）
- **AND** 模板中说明 sell 决策 MUST 申报 sell_type（未申报将被校验打回，打回后仍缺默认按 short 处理并如实标注）
