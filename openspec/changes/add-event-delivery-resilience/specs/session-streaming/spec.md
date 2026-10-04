# Delta for session-streaming

## ADDED Requirements

### Requirement: 终态事件优先送达

系统 SHALL 为终态事件（`done` / `report_ready` / `error` / `interrupted`）提供独立于明细事件（thinking_token 等）批量队列的发布路径。终态落库 SHALL 带瞬态重试；终态发布前 SHALL 仅冲刷有界的 pending 明细缓冲（单事务）以保持 `(session_id, seq)` 单调，SHALL NOT 等待未落库的历史明细洪峰排空；会话状态（`sessions.status`）的终态流转 SHALL 与终态事件发布同窗完成且带重试。终态事件的落库与发布 MUST NOT 因明细事件积压被无限期推迟。既有「先落库后 fan-out」与终态 per-run 去重语义 SHALL 保持不变。

#### Scenario: 明细洪峰下终态仍及时落库发布

- **GIVEN** 单会话存在数万 thinking_token 明细的积压（journal 写入或 SSE 消费滞后分钟级）
- **WHEN** 管线完成并发布 `done`
- **THEN** `done` 在 pending 明细缓冲冲刷（单事务）的有界时间内完成落库并获得 seq
- **AND** 订阅者立即可收到 `done`，不依赖积压明细排空
- **AND** `sessions.status` 在同一窗口内流转为 completed（带重试）

#### Scenario: 重连客户端不依赖积压排空即见终态

- **GIVEN** 终态已落库而部分明细事件永久丢失（incident 037 场景）
- **WHEN** 新客户端经 `GET /api/sessions/{id}/stream?after_seq` 重连
- **THEN** 重放后 SHALL 下发终态事件并关闭流
- **AND** 不存在「会话实际完成但任何界面都无法看到完成」的中间态

#### Scenario: 终态去重不因优先路径失效

- **GIVEN** 某轮分析的终态已发布
- **WHEN** 同轮再次发布终态事件
- **THEN** per-run 终态去重（CAS）仍然生效，不产生重复终态

#### Scenario: 图完成后工具消费端压缩缓冲明细

- **GIVEN** ReAct 路径 `run_deep_analysis` 的消费循环中，图流已完成但事件队列仍积压大量 thinking_token 明细
- **WHEN** 图完成信号到达消费循环
- **THEN** 队列中缓冲的 thinking_token 明细 SHALL 允许压缩丢弃（节点边界/工具/终态事件保留），使终态 TOOL_RESULT 在图完成后的有界时间内产生
- **AND** 超时看门狗据此获得图的真实完成状态，不得将排空延迟误判为超时

### Requirement: 发布积压可观测与背压

事件发布链路 SHALL 暴露积压可观测信号：事件队列深度、pending 明细缓冲深度、明细丢弃计数（日志 + 可查询指标）。事件队列满时 SHALL 按事件类别分级处置：thinking_token 明细 SHALL 允许丢弃且每次丢弃 MUST 计数并记录日志（含 session_id）；节点边界（`node_start` / `node_complete`）、工具与搜索（`tool_call` / `tool_result` / `search`）、终态（`done` / `report_ready` / `error` / `interrupted`）事件 MUST NOT 因队列满被丢弃，MUST 保证其落库与 fan-out（必要时阻塞生产端而非丢弃）。无计数、无日志的静默丢弃 MUST NOT 存在。

#### Scenario: 队列满时明细被丢弃且可观测

- **GIVEN** 事件队列已满（消费速率低于生产速率）
- **WHEN** thinking_token 明细事件到达
- **THEN** 该事件被丢弃，丢弃计数递增并输出含 session_id 的日志
- **AND** 明细稀疏不产生前端 seq 空洞卡死（既有 resync 语义覆盖）

#### Scenario: 队列满时边界与终态事件不被丢弃

- **GIVEN** 事件队列已满
- **WHEN** `node_complete` 或终态事件到达
- **THEN** 事件 MUST NOT 被静默丢弃：生产端以有界等待入队，事件最终落库并 fan-out
- **AND** `(session_id, seq)` 单调性保持

#### Scenario: 积压状态可查询

- **GIVEN** 单会话事件队列或 pending 缓冲深度超过阈值
- **THEN** 队列深度与明细丢弃计数可经日志或指标查询，丢弃规模可事后审计
