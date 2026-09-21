## MODIFIED Requirements

### Requirement: 交易决策节渲染操作参数

报告的「交易决策」节 SHALL 渲染 `TradeDecision` 的操作参数：方向、置信度、仓位档位为必含字段；`reasoning` 为必含字段。渲染 SHALL 与决策落库（decision-outcome 日批结算）消费的同一 JSON 对象同源，MUST NOT 只渲染自由文本理由而丢弃结构化参数。非执行动作（watch/hold）的 `inaction_reason` 与 `reeval_triggers`（require-watch-hold-rationale）为必渲染对象：字段在场时 SHALL 结构化渲染，字段缺失时 SHALL 如实标注「未申报」，MUST NOT 编造条目。

(Previously: 非执行动作的再评估触发条件无结构化字段，报告只在决策节注明「再评估触发条件位于理由文本中，不得凭空编造结构化条目」。)

#### Scenario: buy/sell 决策渲染完整操作参数

- **WHEN** `final_trade_decision` 的 action 为 buy 或 sell，且 `entry_price`/`stop_loss`/`target_price`/`position_size` 均为有效值
- **THEN** 报告「交易决策」节 SHALL 依次渲染方向、置信度、仓位档位、入场价、止损价、目标价、理由
- **THEN** 价位数值 SHALL 与决策 JSON 中的原始值一致（不做四舍五入以外的加工）

#### Scenario: watch/hold 决策渲染结构化不行动理由与再评估条件

- **WHEN** `final_trade_decision` 的 action 为 watch 或 hold
- **THEN** 报告 SHALL 渲染方向、置信度、仓位档位、理由，MUST NOT 渲染入场/止损/目标价行（watch/hold 语义上无建仓参数）
- **THEN** 决策对象携带 `inaction_reason` 时，报告 SHALL 渲染「不行动原因」行，内容与决策 JSON 原始值一致
- **THEN** 决策对象携带非空 `reeval_triggers` 时，报告 SHALL 渲染「再评估触发条件」编号条目，条目内容与决策 JSON 原始值逐条一致
- **THEN** 字段缺失时报告 SHALL 渲染「未申报」如实标注，MUST NOT 编造结构化条目

#### Scenario: watch/hold 旧决策对象兼容渲染

- **WHEN** `final_trade_decision` 为 watch 或 hold 且为历史形态（无 `inaction_reason`/`reeval_triggers` 字段）
- **THEN** 报告 SHALL 正常渲染方向、置信度、仓位档位、理由，不行动原因与再评估触发条件行 SHALL 标注「未申报」
- **AND** 渲染 MUST NOT 因字段缺失抛异常
