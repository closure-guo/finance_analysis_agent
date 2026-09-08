## ADDED Requirements

### Requirement: 决策落库

每个产出的 `TradeDecision` SHALL 同步落 `decision_log` 表，记录决策关键字段、时间戳与原 Langfuse trace 关联，初始 `status="open"`。落库 SHALL NOT 阻断业务管线（旁路失败仅日志，不影响报告产出）。

#### Scenario: 决策产出即落库

- **WHEN** Fund Manager 产出 `TradeDecision` 并写入 state
- **THEN** 系统 SHALL 同步向 `decision_log` 插入一条记录
- **AND** 记录含 decision_id / session_id / langfuse_trace_id / timestamp / ticker / action / entry_price / stop_loss / target_price / confidence / position_size
- **AND** `status` 初始为 `open`

#### Scenario: 落库失败不阻断业务

- **GIVEN** SQLite 写入异常
- **WHEN** 决策落库失败
- **THEN** 业务管线 SHALL 正常完成报告产出
- **AND** 失败仅记 ERROR 日志

#### Scenario: trace 关联可追溯

- **WHEN** 落库完成
- **THEN** `langfuse_trace_id` SHALL 指向产生该决策的 Langfuse trace
- **AND** 后续可反向联查

### Requirement: 事后行情追踪

系统 SHALL 运行日批定时任务（每个交易日收盘后），对所有 `status=open` 的决策拉取标的与基准的日 K 行情，按结算规则更新状态（`hit_stop` / `hit_target` / `expired`），记录实际结算价、持有期收益与基准收益。任务 SHALL 幂等（重复执行不重复结算）且失败可重试。

#### Scenario: 止损触发结算

- **GIVEN** 某 open 决策设了 stop_loss
- **WHEN** 持有期某日最低价 ≤ stop_loss
- **THEN** 该决策 `status` SHALL 更新为 `hit_stop`
- **AND** `settle_price` / `hold_days` / `decision_return` / `benchmark_return` / `decision_excess` 记录实际值

#### Scenario: 目标达成结算

- **GIVEN** 某 open 决策设了 target_price
- **WHEN** 持有期某日最高价 ≥ target_price
- **THEN** 该决策 `status` SHALL 更新为 `hit_target`

#### Scenario: 止损与目标同日触及

- **WHEN** 同一交易日最低价 ≤ stop_loss 且最高价 ≥ target_price
- **THEN** SHALL 按止损优先结算（`hit_stop`），保守处理

#### Scenario: 超期强制结算

- **GIVEN** 持仓天数超过 `MAX_HOLD_DAYS`（默认 20 交易日）
- **WHEN** 未触及止损 / 目标
- **THEN** 该决策 `status` SHALL 更新为 `expired`
- **AND** `settle_price` 用结算日收盘价

#### Scenario: 幂等结算

- **GIVEN** 某 decision 已 `settled_at` 非空
- **WHEN** 定时任务再次处理
- **THEN** SHALL 跳过该 decision，不重复结算 / 不重复上报 Score

#### Scenario: 行情缺失重试

- **WHEN** 某标的当日行情拉取失败
- **THEN** 该决策本次跳过，下次任务重试
- **AND** 连续 N 日（可配）无数据 SHALL 标记 `data_stale` 告警

### Requirement: 决策效果 Score 反向上报

决策结算后系统 SHALL 向 Langfuse 反向上报三个 Score，关联原 `langfuse_trace_id`：`decision_hit`（方向是否正确，BOOLEAN）、`decision_return`（方向符号化实际收益率，NUMERIC）、`decision_excess`（相对基准超额，NUMERIC）。上报失败（trace 不存在 / 已过期）SHALL 仅记 WARN，不阻断结算。

#### Scenario: 结算即上报 Score

- **WHEN** 决策结算完成（status 转为 hit_stop/hit_target/expired）
- **THEN** 系统 SHALL 调 `langfuse.score(trace_id=..., name=..., value=...)` 上报三个 Score
- **AND** comment 含 settle_price / hold_days / 基准收益摘要

#### Scenario: 方向符号化

- **WHEN** action 为 `buy`
- **THEN** `decision_return = (settle_price - entry_price) / entry_price`
- **WHEN** action 为 `sell` / `hold` / `watch`
- **THEN** `decision_return` SHALL 取负（即建议不买 / 卖出后下跌为正收益）
- **AND** `decision_hit = decision_return > 0`

#### Scenario: 基准超额

- **WHEN** 上报 decision_excess
- **THEN** `decision_excess = decision_return - benchmark_return`
- **AND** benchmark_return 对 sell/hold/watch 方向同样符号化取负后再比

#### Scenario: trace 不可查容错

- **GIVEN** langfuse_trace_id 对应 trace 已过期或不存在
- **WHEN** 上报 Score
- **THEN** SHALL 记 WARN 不阻断
- **AND** decision_log 的收益字段仍正常记录

### Requirement: A 股异常结算规则

系统 SHALL 对 A 股特有情形（涨跌停一字板、停牌）定义明确结算规则：触及止损 / 目标但一字板未成交时，结算价 SHALL 用次日首个可成交价（递延至涨跌停打开）；停牌日 SHALL 不计入持有期、持仓周期顺延、结算价用复牌首日收盘。

#### Scenario: 一字跌停止损未成交

- **GIVEN** 某 buy 决策触及 stop_loss，当日为一字跌停（全天未成交）
- **WHEN** 结算
- **THEN** settle_price SHALL 用跌停打开后首个可成交价（如次日开盘）
- **AND** hold_days 含等待日
- **AND** decision_return 按实际可成交价计算（非 stop_loss 价）

#### Scenario: 停牌持仓期顺延

- **GIVEN** 持有期内标的停牌 N 日
- **WHEN** 结算
- **THEN** 停牌日 SHALL 不计入 hold_days
- **AND** MAX_HOLD_DAYS 周期 SHALL 顺延 N 日
- **AND** 结算价用复牌首日收盘

#### Scenario: 复权处理

- **WHEN** 拉取日 K
- **THEN** SHALL 使用前复权（adjust="qfq"）
- **AND** 分红除权日的精确除权处理首版近似，记 Open Question

### Requirement: 基准对比

系统 SHALL 以沪深 300（000300）同期收益率为默认基准，使决策效果可对照大盘。基准代码与持仓周期 `MAX_HOLD_DAYS` SHALL 可经配置覆盖。

#### Scenario: 基准收益计算

- **WHEN** 决策结算
- **THEN** SHALL 同期拉取沪深 300 日 K
- **AND** `benchmark_return = (基准结算价 - 基准决策时价) / 基准决策时价`

#### Scenario: 配置可覆盖

- **GIVEN** 配置项 `BENCHMARK_CODE` 与 `MAX_HOLD_DAYS`
- **WHEN** 运维设置非默认值
- **THEN** 结算 SHALL 使用配置值（如换行业指数、调周期）

#### Scenario: 基准行情缺失

- **WHEN** 基准日 K 拉取失败
- **THEN** `benchmark_return` / `decision_excess` SHALL 记 null
- **AND** `decision_return` / `decision_hit` 仍正常记录
