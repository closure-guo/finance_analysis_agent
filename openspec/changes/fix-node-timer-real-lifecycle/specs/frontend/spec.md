# Delta Spec: frontend（fix-node-timer-real-lifecycle）

## MODIFIED Requirements

### Requirement: Pipeline Progress Display

系统 SHALL 在深度分析期间展示管线进度与节点计时。节点计时 SHALL 优先使用后端提供的真实生命周期时间戳（server_start_ts / server_end_ts / server_duration_ms）；当后端未提供时（stub、fast path、历史会话），SHALL 回退到前端事件到达时间戳计算，保持向后兼容。

#### Scenario: 节点计时优先使用后端真实时间戳

- **GIVEN** 管线 UI 已渲染且收到 node_complete 事件
- **WHEN** 该事件携带 server_duration_ms（或 server_start_ts + server_end_ts）
- **THEN** 对应节点的 durationMs SHALL 采用后端真实耗时
- **AND** 快速节点显示真实毫秒级耗时（<1s 时 formatDurationMs 显示 "0:00"）
- **AND** 慢节点（LLM）显示真实秒级耗时

#### Scenario: 节点开始时间戳优先使用后端入口时间

- **GIVEN** 收到 node_start 事件
- **WHEN** 该事件携带 server_start_ts
- **THEN** 节点的 startedAt SHALL 采用 server_start_ts 而非前端 Date.now()
- **AND** 当前运行节点的实时已运行时长基于该时间戳计算

#### Scenario: 无后端时间戳时回退前端计算

- **GIVEN** 收到 node_complete 事件
- **WHEN** 该事件未携带任何 server_* 时间戳字段（stub / fast path / 历史会话）
- **THEN** 前端 SHALL 回退到现有 Date.now() 到达时间戳计算 durationMs
- **AND** 现有 E2E 与单测行为不回归
