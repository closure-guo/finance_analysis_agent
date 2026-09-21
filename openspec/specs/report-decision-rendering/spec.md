# report-decision-rendering Specification

## Purpose
TBD - created by archiving change report-render-operational-params. Update Purpose after archive.
## Requirements
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

### Requirement: 参数缺失时诚实标注

操作参数为 0、null 或缺失时，报告 SHALL 如实标注「未提供」，MUST NOT 静默跳过该行，MUST NOT 以占位数据（如 0）冒充有效价位。

#### Scenario: 价位缺失标注

- **WHEN** action 为 sell 但 `stop_loss` 与 `target_price` 均为 0（风险辩论中保守方定性为「风控半成品」的形态）
- **THEN** 报告 SHALL 在止损/目标价行渲染「未提供」
- **THEN** 报告 MUST NOT 因此省略仓位档位或其他有效参数的渲染

### Requirement: 价位修正标注保留

当决策对象携带 `price_level_corrected` 标记时，报告 SHALL 保留既有「价位修正」行（toolize-price-levels 的可观测语义），MUST NOT 因新增参数渲染而丢失该标注。

#### Scenario: 修正过的价位渲染

- **WHEN** 决策对象 `price_level_corrected` 为真且 `price_level_correction_reason` 非空
- **THEN** 报告「交易决策」节 SHALL 在参数行之后渲染价位修正说明（含修正原因）

### Requirement: 派生指标由代码确定性计算

buy/sell 决策的派生指标（赔率 = (target−entry)/(entry−stop)、止损距离百分比 = (entry−stop)/entry）SHALL 由渲染代码按参数原值计算，MUST NOT 取用决策 `reasoning` 文本中 LLM 自行心算的同类数值；LLM 计算值与代码计算值不一致时，报告 SHALL 以代码计算值为准。

#### Scenario: 赔率渲染以代码计算为准

- **WHEN** buy 决策 entry=52.0、stop=47.8、target=60.0，且 reasoning 文本中出现「风险收益比约1.9:1」
- **THEN** 报告 SHALL 渲染代码计算的赔率值（8/4.2 ≈ 1.90）与止损距离（8.1%），数值来源为参数原值的确定性运算
- **THEN** 即使 reasoning 中自算赔率有误，报告 MUST NOT 采用 reasoning 文本中的数值

