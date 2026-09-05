# Delta for decision-outcome

> 本 delta 以 MODIFIED 演进 `decision-outcome-tracking`（未归档提案）的需求。sync 顺序：decision-outcome-tracking 须先归档进入主规范库，本 delta 的 MODIFIED 再应用（见 design.md）。

## MODIFIED Requirements

### Requirement: 决策落库

每个产出的观点 SHALL 写入 `predictions` 表（取代原 `decision_log`）：不再只记 approve，**reject、hold/watch、neutral 方向的观点同样落库**（全量记录）。记录 SHALL 含观点快照（rationale_snapshot，写入后冻结）、direction（action 映射：buy→long、sell→short、hold/watch→neutral）、confidence、entry_price（参考价，注明口径）、source_type（backtest/live）、权威 created_at（服务端生成）。写入 SHALL NOT 阻断业务管线（旁路失败仅日志，不影响报告产出）。
(Previously: 每个产出的 TradeDecision SHALL 同步落 decision_log 表，仅 approve 记录，初始 status="open"，普通可改写表。)

#### Scenario: 决策产出即落库

- **WHEN** Fund Manager 产出任一观点（`TradeDecision` 并写入 state）
- **THEN** 系统 SHALL 同步向 `predictions` 插入一条记录
- **AND** 记录含 langfuse_trace_id / created_at（服务端权威）/ ticker / direction / entry_price / confidence / source_type 等
- **AND** 观点保持 open 直至判定结算

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

#### Scenario: 止损触发结算

- **GIVEN** 旧规则下价格触及止损价的 open 观点
- **WHEN** 判定任务处理
- **THEN** SHALL NOT 以止损触发提前结算（horizon 判定取代止损/目标/超期路径）
- **AND** 结算统一以 horizon 到点的区间超额收益为准

#### Scenario: 目标达成结算

- **GIVEN** 旧规则下价格触及目标价的 open 观点
- **WHEN** 判定任务处理
- **THEN** SHALL NOT 以目标达成触发提前结算
- **AND** 判定统一以 horizon 终点区间超额收益为准

#### Scenario: 止损与目标同日触及

- **GIVEN** 同一交易日价格既触及止损价又触及目标价
- **WHEN** 判定任务处理
- **THEN** SHALL NOT 适用「同日按止损优先」规则（该规则随旧结算路径一并取代）

#### Scenario: 超期强制结算

- **GIVEN** 某 open 观点持有天数超过旧 `MAX_HOLD_DAYS`（20 交易日）
- **WHEN** 判定任务处理
- **THEN** SHALL NOT 按超期强制以结算日收盘结算
- **AND** 该观点保持 open 至 horizon 到点（或被 superseded）

#### Scenario: 幂等结算

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

#### Scenario: 一字跌停止损未成交

- **GIVEN** 旧规则下一字跌停未成交的止损递延场景
- **WHEN** 新判定任务处理
- **THEN** SHALL NOT 适用止损递延语义（止损路径已被 horizon 判定取代）
- **AND** 若 horizon 到点当日为涨跌停一字板，判定 SHALL 顺延至打开后首个可成交交易日

#### Scenario: 停牌持仓期顺延

- **GIVEN** 持有期内标的停牌 N 日
- **WHEN** 判定任务处理
- **THEN** 停牌日 SHALL 不计入 horizon 交易日数（horizon 顺延 N 个交易日）
- **AND** 长期停牌/退市/长期无行情 SHALL 标记 unresolvable（见上）

#### Scenario: 复权处理

- **WHEN** 拉取日 K 计算区间收益
- **THEN** SHALL 使用后复权（adj）口径
- **AND** 分红除权处理遵循后复权口径，不做首版近似

## REMOVED Requirements

### Requirement: 决策战绩页面

> 被本 delta 新增的「战绩页面」（track-record 能力，/track-record）取代：旧 /decisions 页面废弃、路由改指新页，仅保留决策查询 API（`GET /api/decisions` 与 `/api/decisions/stats`）与前端共存，页面行为与数据口径以后者为准。

#### Scenario: 旧页面废弃

- **WHEN** 用户访问 /decisions 或 /track-record
- **THEN** SHALL 渲染统一的新战绩页面（TrackRecordPage）
- **AND** 旧 DecisionCenter 页面 SHALL 不再存在（/decisions 路由指向新页面）

#### Scenario: API 共存

- **WHEN** 前端或外部仍调用 `GET /api/decisions` 与 `/api/decisions/stats`
- **THEN** 两端点 SHALL 继续可用并返回既有契约（决策列表现状/过滤参数/统计口径不变）
