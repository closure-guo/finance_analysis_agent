# Delta for session-streaming

## MODIFIED Requirements

### Requirement: 发布积压可观测与背压

(Previously: 事件队列满时按事件类别分级处置——thinking 明细可丢弃并计数，节点边界/工具/终态事件 MUST NOT 因队列满被丢弃、以有界等待保证落库与 fan-out；积压信号含队列深度、pending 缓冲深度与丢弃计数，可经日志或指标查询。)

事件发布链路 SHALL 暴露积压可观测信号：事件队列深度、pending 明细缓冲深度、明细丢弃计数（日志 + 可查询指标）。事件队列满时 SHALL 按事件类别分级处置：thinking_token 明细 SHALL 允许丢弃且每次丢弃 MUST 计数并记录日志（含 session_id）；节点边界（`node_start` / `node_complete`）、工具与搜索（`tool_call` / `tool_result` / `search`）、终态（`done` / `report_ready` / `error` / `interrupted`）事件 MUST NOT 因队列满被丢弃，MUST 保证其落库与 fan-out（必要时阻塞生产端而非丢弃）。无计数、无日志的静默丢弃 MUST NOT 存在。

发布链路 SHALL 具备连续投递失败熔断降级：同一会话连续 N 次（默认 3）undeliverable（有界等待超时）后，非终态事件 SHALL 降级为立即丢弃并计数（计入 `breaker_degraded` 桶），MUST NOT 再逐个执行有界等待；终态事件与流终结哨兵 SHALL 保留有界等待入队路径，MUST NOT 被熔断丢弃；任一事件成功入队 SHALL 重置连续失败计数。被熔断丢弃的每次事件 MUST 计数并记录日志，MUST NOT 静默丢弃。

积压状态 SHALL 提供运维查询出口：经只读运维端点（`GET /api/v1/ops/stream-backlog`）返回全部活跃会话的订阅者队列深度、订阅者数、丢弃计数与最后 seq，使队列深度与丢弃规模可事后审计。

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

#### Scenario: 连续 undeliverable 触发熔断降级

- **GIVEN** 消费端长期停滞，同一会话已连续 3 次事件入队超时（undeliverable）
- **WHEN** 第 4 个非终态事件到达
- **THEN** 该事件立即丢弃并计入 `breaker_degraded` 桶（含日志），MUST NOT 再等待有界超时
- **AND** 终态事件或流终结哨兵到达时仍保留有界等待入队路径

#### Scenario: 成功入队重置熔断计数

- **GIVEN** 连续 2 次 undeliverable 后，消费者恢复、下一事件成功入队
- **WHEN** 此后再发生 1 次 undeliverable
- **THEN** 熔断不触发（连续计数已重置，未达阈值）

#### Scenario: 积压状态可查询

- **GIVEN** 单会话事件队列或 pending 缓冲深度超过阈值
- **THEN** 队列深度与明细丢弃计数可经日志或指标查询，丢弃规模可事后审计
- **AND** `GET /api/v1/ops/stream-backlog` 返回活跃会话的订阅者队列深度、丢弃计数与 last_seq
