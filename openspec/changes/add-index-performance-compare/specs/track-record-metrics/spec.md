# Delta for track-record-metrics

## MODIFIED Requirements

### Requirement: 每日盯市记录

系统 SHALL 每个交易日对全部 status=open 观点写入 `daily_marks` 记录(mark_date/mark_price/cum_return/cum_excess),停牌或缺数据时跳过且不报错。盯市任务 SHALL 在同一日批内对 INDEX_COMPARE_UNIVERSE 指数集拉取当日收盘并幂等写入 `index_closes`(语义细则见 index-comparison 能力);指数落库 SHALL NOT 改变本需求盯市记录的行为与汇总口径。
(Previously: 仅要求 open 观点写 daily_marks,无指数收盘落库职责。)

#### Scenario: 正常盯市

- **WHEN** 日批 `daily-marking` 任务运行且 open 观点对应标的有当日收盘价
- **THEN** 写入一条 daily_marks,cum_return 与 cum_excess 相对 entry_price 与基准同步期收益计算

#### Scenario: 缺数据容错

- **WHEN** 标的当日无行情(停牌/接口失败)
- **THEN** 该观点当日不产生 daily_marks,任务继续处理其余观点且整体返回成功

#### Scenario: 指数收盘顺带落库不影响盯市

- **WHEN** 日批运行,指数集收盘拉取全部失败
- **THEN** daily_marks 与 equity_curve 行为不变,盯市任务状态仍为成功
- **AND** 失败详情只出现在日志 WARNING,不进入 marked/skipped/errors 汇总
