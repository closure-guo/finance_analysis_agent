## ADDED Requirements

### Requirement: Terminal Event Per-Run Deduplication

系统 SHALL 对终态事件（done/interrupted/error）实施 per-run 去重：同一轮运行（单次 `StreamRegistry.start()` 创建的 `SessionStream` 生命周期）内，首个终态事件正常写入 journal 并 fan-out 给订阅者；同轮内后续终态事件被丢弃（返回 0）。去重作用域 SHALL 为单次运行的内存标志，SHALL NOT 跨越同一会话的多轮追问--每轮运行的终态事件独立发送。

#### Scenario: 同一轮运行内重复终态事件去重

- **GIVEN** 某会话的生成任务正在运行，生成逻辑已显式发布 `done` 事件
- **WHEN** `_run_task` 正常完成后自动发布 `done` 事件
- **THEN** 第二个 `done` 被去重丢弃（返回 0），不写入 journal、不 fan-out
- **AND** 订阅者仅收到一个 `done` 事件

#### Scenario: 多轮追问每轮独立发送终态事件

- **GIVEN** 会话第一轮生成已完成，journal 中存在第一轮的 `done` 事件
- **WHEN** 用户追问发起第二轮生成，第二轮正常完成并发布 `done` 事件
- **THEN** 第二轮的 `done` 事件 SHALL 正常写入 journal 并 fan-out 给订阅者
- **AND** 前端收到第二轮的 `done` 事件并据此清除流式游标

#### Scenario: 第二轮中断事件正常下发

- **GIVEN** 会话第一轮生成已完成，journal 中存在第一轮的 `done` 事件
- **WHEN** 用户追问发起第二轮生成，用户在第二轮运行中点击停止按钮
- **THEN** 第二轮的 `interrupted` 事件 SHALL 正常写入 journal 并 fan-out 给订阅者
- **AND** 前端收到 `interrupted` 事件并据此清除流式状态、回到可追问态

#### Scenario: 第二轮 error 事件正常下发

- **GIVEN** 会话第一轮生成已完成，journal 中存在第一轮的 `done` 事件
- **WHEN** 用户追问发起第二轮生成，第二轮生成过程中发生异常
- **THEN** 第二轮的 `error` 事件 SHALL 正常写入 journal 并 fan-out 给订阅者
- **AND** 前端收到 `error` 事件并据此展示错误信息、清除流式状态
