# Delta for decision-outcome

> 本 delta 以 MODIFIED 演进 `decision-outcome-tracking`（未归档提案）的需求。sync 顺序：decision-outcome-tracking 须先归档进入主规范库，本 delta 的 MODIFIED 再应用（见 design.md）。

## MODIFIED Requirements

### Requirement: 决策落库

每个产出的观点 SHALL 写入 `predictions` 表（取代原 `decision_log`）：不再只记 approve，**reject、hold/watch、neutral 方向的观点同样落库**（全量记录）。记录 SHALL 含观点快照（rationale_snapshot，写入后冻结）、direction（action 映射：buy→long、sell→short、hold/watch→neutral）、confidence、entry_price（参考价，注明口径）、source_type（backtest/live）、权威 created_at（服务端生成）。写入 SHALL NOT 阻断业务管线（旁路失败仅日志，不影响报告产出）。
(Previously: 每个产出的 TradeDecision SHALL 同步落 decision_log 表，仅 approve 记录，初始 status="open"，普通可改写表。)

#### Scenario: 全量观点落库（含 reject）

- **WHEN** Fund Manager 产出任一决策（approve/reject/return）
- **THEN** 系统 SHALL 同步向 `predictions` 插入一条记录
- **AND** direction SHALL 由 action 映射（buy→long、sell→short、hold/watch→neutral）
- **AND** rationale_snapshot SHALL 冻结含当时完整分析原文

#### Scenario: 落库失败不阻断业务

- **GIVEN** SQLite 写入异常
- **WHEN** 观点落库失败
- **THEN** 业务管线 SHALL 正常完成报告产出
- **AND** 失败仅记 ERROR 日志

#### Scenario: trace 关联可追溯

- **WHEN** 落库完成
- **THEN** `langfuse_trace_id` SHALL 指向产生该观点的 Langfuse trace
- **AND** 后续可反向联查

#### Scenario: 无可靠入场价存档不计分

- **GIVEN** 某观点无可靠 entry_price（quote 与 kline 均不可得）
- **WHEN** 落库
- **THEN** SHALL 存档但不进入战绩统计（缺可判定要素）
- **AND** SHALL 记 WARN 日志

### Requirement: 事后行情追踪

系统 SHALL 运行日批判定任务（每个交易日收盘后），对所有 `open` 观点按 track-record 判定规则结算：默认 horizon T+252 交易日（观点自带 horizon_days 则以其为准，上限 1 年）；方向相反或目标价不同的新观点触发旧观点立即结算（superseded）；long 区间超额 > +2% → resolved_win，< −2% → resolved_loss，±2% 内 → resolved_neutral；short 对称。任务 SHALL 幂等（重复执行不重复结算）且失败可重试。
(Previously: 对所有 status=open 决策按止损/目标/超期规则更新状态 hit_stop/hit_target/expired，记录结算价、持有期收益与基准收益。)

#### Scenario: 到期判定（horizon 终点）

- **GIVEN** 某 open long 观点到达 horizon 终点
- **WHEN** 判定任务处理
- **THEN** 按区间超额收益判定 resolved_win / resolved_loss / resolved_neutral
- **AND** exit_price / raw_return / excess_return 记录实际值

#### Scenario: 提前结算（superseded）

- **WHEN** 对同一标的发出方向相反或目标价不同的新观点
- **THEN** 旧观点 SHALL 立即以当前价格结算
- **AND** resolution_rule SHALL 记录为 superseded

#### Scenario: 幂等判定

- **GIVEN** 某观点已 resolved 或 unresolvable
- **WHEN** 判定任务再次处理
- **THEN** SHALL 跳过该观点，不重复结算 / 不重复上报 Score

#### Scenario: 行情缺失重试

- **WHEN** 某标的当日行情拉取失败
- **THEN** 该观点本次跳过，下次任务重试
- **AND** 连续 N 日（可配）无数据 SHALL 标记 unresolvable 告警

### Requirement: A 股异常结算规则

系统 SHALL 对 A 股特有情形在新判定规则下明确处理：停牌/退市/长期无行情 SHALL 标记 `unresolvable`（计入样本量，不计入胜率，UI 单独标识）；一字涨跌停未成交时，结算价 SHALL 用跌停/涨停打开后首个可成交价。
(Previously: 涨跌停一字板触及止损/目标但一字板未成交时递延至涨跌停打开；停牌日不计入持有期、持仓周期顺延、结算价用复牌首日收盘。)

#### Scenario: 停牌不可判定

- **GIVEN** 持有期内标的停牌或长期无行情
- **WHEN** 判定任务处理
- **THEN** 该观点 SHALL 标记 unresolvable
- **AND** 计入样本量，不计入胜率

#### Scenario: 一字板未成交结算

- **GIVEN** 某观点触及结算但当日为一字涨跌停（全天未成交）
- **WHEN** 结算
- **THEN** 结算价 SHALL 用涨跌停打开后首个可成交价
- **AND** 收益按实际可成交价计算

#### Scenario: 复权处理

- **WHEN** 拉取日 K 计算区间收益
- **THEN** SHALL 使用后复权（adj）口径
- **AND** 分红除权处理遵循后复权口径，不做首版近似
