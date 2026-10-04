# Delta for session-persistence

## ADDED Requirements

### Requirement: SQLite 瞬态错误重试

`session_store` 的连接获取层 SHALL 对瞬态 SQLite 错误（`unable to open database file`、`database is locked`、`disk I/O error`）做有界短重试（有限次数 + 短退避），覆盖全部读写函数而非仅事件 append 路径。重试耗尽 SHALL 向调用方抛出原异常（显式失败），MUST NOT 静默吞掉造成「假写成功」。终态关键路径（终态事件落库、`sessions.status` 流转、`report_markdown` 落库）的调用方 SHALL 在重试耗尽后执行兜底处置（错误日志 + 状态显式置错），MUST NOT 留下「管线已完成但会话状态缺失」且无任何日志的中间态。

#### Scenario: 瞬断自愈窗口内写成功

- **GIVEN** SQLite 数据库文件短暂不可打开（如 bind mount 瞬断，约 2 秒内自愈）
- **WHEN** 任一 `session_store` 读写函数被调用
- **THEN** 连接获取层重试后 SHALL 成功执行，调用方无感知

#### Scenario: 重试耗尽显式失败

- **GIVEN** 瞬态错误持续超过重试窗口
- **WHEN** 写函数被调用
- **THEN** SHALL 抛出原异常而非静默返回成功
- **AND** 终态关键路径调用方 SHALL 记录错误日志并显式处置（置错或重试兜底）

#### Scenario: 非 append 热路径同样受保护

- **GIVEN** `update_session_status` / `update_pipeline_timelines` / `update_pipeline_snapshot` 在调用时命中瞬态错误
- **THEN** SHALL 经同一连接获取重试机制处置，而非直接失败
