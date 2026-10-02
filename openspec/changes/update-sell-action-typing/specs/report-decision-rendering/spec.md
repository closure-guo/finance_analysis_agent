# Delta for report-decision-rendering

## MODIFIED Requirements

### Requirement: 交易决策节渲染操作参数

报告的「交易决策」节 SHALL 渲染 `TradeDecision` 的操作参数：方向、置信度、仓位档位为必含字段；`reasoning` 为必含字段。渲染 SHALL 与决策落库（decision-outcome 日批结算）消费的同一 JSON 对象同源，MUST NOT 只渲染自由文本理由而丢弃结构化参数。`reeval_triggers` 为全部 action 的必渲染对象：watch/hold 另渲染 `inaction_reason`；字段在场时 SHALL 结构化渲染，字段缺失时 SHALL 如实标注「未申报」，MUST NOT 编造条目。

sell 决策 SHALL 按 `sell_type` 分模板渲染（update-sell-action-typing，issue #188：减仓与做空是不同执行结构，共用建仓模板对持有者语义不通）：

- `sell_type="exit"`（持有者减仓）：渲染「减仓节奏」行（`exit_schedule` 原文；缺失如实「未申报」），MUST NOT 渲染入场/止损/目标价行（exit 无新建仓参数，与 watch/hold 的无建仓参数语义同型）；重新介入条件由 `reeval_triggers` 承载（既有渲染不变）；
- `sell_type="short"`（做空建仓）：按 buy/sell 既有参数行渲染（entry/stop/target + 派生指标）；
- `sell_type` 为 None（历史/未申报形态）：按 short 模板渲染（保守默认，与价位必填校验的默认推导一致）。

(Previously: sell 与 buy 共用一套参数行模板，无 sell_type 概念。)

#### Scenario: buy/sell 决策渲染完整操作参数

- **WHEN** `final_trade_decision` 的 action 为 buy，或 action 为 sell 且 `sell_type="short"`，且 `entry_price`/`stop_loss`/`target_price`/`position_size` 均为有效值
- **THEN** 报告「交易决策」节 SHALL 依次渲染方向、置信度、仓位档位、入场价、止损价、目标价、再评估触发条件、理由
- **THEN** 价位数值 SHALL 与决策 JSON 中的原始值一致（不做四舍五入以外的加工）

#### Scenario: exit（减仓）渲染减仓节奏而非建仓参数

- **WHEN** `final_trade_decision` 的 action 为 sell 且 `sell_type="exit"`，携带 `exit_schedule="分两批：现价减半、跌破600清仓"`
- **THEN** 报告 SHALL 渲染方向（卖出·减仓类标识）、置信度、仓位档位、「减仓节奏: 分两批：现价减半、跌破600清仓」、再评估触发条件（重新介入条件）、理由
- **THEN** 报告 MUST NOT 渲染入场价/止损价/目标价行（exit 语义无新建仓参数）
- **WHEN** `exit_schedule` 缺失
- **THEN** 「减仓节奏」行 SHALL 如实渲染「未申报」，MUST NOT 编造

#### Scenario: sell 未申报 sell_type 按默认模板渲染

- **WHEN** action 为 sell 且 `sell_type` 为 None（历史决策对象或申报缺失的默认形态）
- **THEN** 报告 SHALL 按 short 模板渲染既有参数行（行为与现状一致，历史报告兼容）

#### Scenario: buy/sell 决策再评估触发条件缺失标注

- **WHEN** `final_trade_decision` 的 action 为 buy 或 sell，且清洗后 `reeval_triggers` 为空（含「已打回仍未申报」终检形态）
- **THEN** 报告 SHALL 渲染「再评估触发条件: 未申报」行，MUST NOT 整行省略，MUST NOT 编造条目

#### Scenario: watch/hold 决策渲染结构化不行动理由与再评估条件

- **WHEN** `final_trade_decision` 的 action 为 watch 或 hold
- **THEN** 报告 SHALL 渲染方向、置信度、仓位档位、理由，MUST NOT 渲染入场/止损/目标价行（watch/hold 语义上无建仓参数）
- **THEN** 决策对象携带 `inaction_reason` 时，报告 SHALL 渲染「不行动原因」行，内容与决策 JSON 原始值一致
- **THEN** 决策对象携带非空 `reeval_triggers` 时，报告 SHALL 渲染「再评估触发条件」编号条目，条目内容与决策 JSON 原始值逐条一致
- **THEN** 字段缺失时报告 SHALL 渲染「未申报」如实标注，MUST NOT 编造结构化条目
