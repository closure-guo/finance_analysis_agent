# decision-backtest Specification

## Purpose

交易决策的历史离线回放评估：用历史数据重演完整管线，以投资绩效指标与统计显著性回答"这套系统历史上做决策赚不赚钱"，为 prompt/模型/架构变更提供离线、可重复、即时的验证手段。与 `decision-outcome`（在线向前追踪）互补：本 capability 向后重演历史，decision-outcome 向前跟踪未来。

## ADDED Requirements

### Requirement: 历史离线回放

系统 SHALL 提供离线回放器：以指定历史日期为决策日，管线数据输入截断至该日之前的可得数据（含财报披露滞后近似），固定 prompt 版本与模型版本，产出当日 TradeDecision 并按持仓语义结算收益。回放器 SHALL 记录每次回放的"数据快照时点"，使前视偏差可审计。

#### Scenario: 时点截断

- **GIVEN** 回放决策日为 T
- **WHEN** 回放器构建管线输入
- **THEN** 所有行情、财报、宏观、新闻数据 SHALL 只含 T 日收盘前可得部分
- **AND** 财报数据 SHALL 按披露日（而非报告期）判断可得性

#### Scenario: 可审计快照

- **WHEN** 一次回放完成
- **THEN** 结果 SHALL 携带数据快照时点、prompt 版本、模型版本标识，支持事后审计前视偏差

### Requirement: 绩效指标与基线对比

回放评估 SHALL 输出绩效四指标：累计收益（CR）、年化收益（ARR）、夏普比率（Sharpe）、最大回撤（MDD），并与基线策略对比：Buy-and-Hold、MACD、KDJ、RSI 规则策略（复用 `metrics/technical.py` 既有实现）。结算语义（涨跌停递延、停牌顺延、前复权、方向符号化）SHALL 复用 `decision-outcome` 的 A 股异常结算规则，SHALL NOT 另造一套。

#### Scenario: 四指标对比报告

- **WHEN** 一批回放完成
- **THEN** 报告 SHALL 给出系统与各基线的 CR/ARR/Sharpe/MDD 对照表

#### Scenario: 结算语义一致

- **WHEN** 回放结算遇到涨跌停、停牌、分红除权
- **THEN** 处理规则 SHALL 与 `decision-outcome` 的在线结算规则一致（一字板递延、停牌期不计入持仓、前复权日 K）

### Requirement: 分层市场状态抽样

回放样本 SHALL 按市场状态分层：至少覆盖单边上涨、单边下跌、震荡三种 regime，且至少含一段下跌市；每种 regime SHALL 抽样 ≥10 只标的。SHALL NOT 仅在单边行情样本上汇报绩效结论。

#### Scenario: 分层覆盖

- **WHEN** 构建回放样本池
- **THEN** 样本 SHALL 标注所属 regime，三种 regime 均有 ≥10 只标的
- **AND** 报告 SHALL 分 regime 展示绩效，SHALL NOT 只给全池汇总

### Requirement: 统计显著性与不确定性报告

绩效对比 SHALL 使用 block bootstrap（B≥1,000，按交易日块重采样，默认块长 20 交易日）报告 Sharpe 与超额收益的置信区间，并附块长敏感性说明。SHALL NOT 只报告点估计。Sharpe > 3 的批次 SHALL 附 sanity check 说明（样本期、回撤构成、换手假设），否则该批次结果标记为无效。

#### Scenario: 置信区间报告

- **WHEN** 生成绩效报告
- **THEN** 系统相对最佳基线的 Sharpe 差 SHALL 带 95% CI
- **AND** CI 含 0 时结论 SHALL 为"无显著差异"

#### Scenario: 异常夏普拦截

- **WHEN** 某批次 Sharpe > 3
- **THEN** 报告 SHALL 强制附 sanity check 段落；缺失时该批次标记 `invalid`，不得用于任何对比结论

### Requirement: 决策一致性测量

同一标的在同一决策日 SHALL 重复回放 n=3 次，报告决策方向一致率（3 次 action 同向的比例）。一致性 SHALL 作为决策质量的独立维度披露，SHALL NOT 被绩效指标掩盖——高绩效低一致性提示结果不可复现。

#### Scenario: 一致率报告

- **WHEN** 回放批次完成
- **THEN** 报告 SHALL 含各标的方向一致率与全池均值
- **AND** 一致率 < 2/3 的标的 SHALL 在绩效汇总中剔除或单独标注
