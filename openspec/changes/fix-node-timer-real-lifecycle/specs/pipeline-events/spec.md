# Delta Spec: pipeline-events（fix-node-timer-real-lifecycle）

## ADDED Requirements

### Requirement: 节点生命周期真实时间戳

系统 SHALL 在图节点的真实生命周期入口与出口发出带后端时间戳的事件，使前端节点计时反映真实执行耗时（而非 updates 流的 chunk 到达间隔）。

#### Scenario: 节点入口发出 node_start 生命周期事件

- **GIVEN** 深度分析管线执行某图节点
- **WHEN** 节点函数开始执行（入口）
- **THEN** 后端 SHALL 通过 custom 流发出 `{"type": "node_start", "node": <node_id>, "ts": <epoch_ms>}`
- **AND** ts 为节点入口的真实后端时间戳

#### Scenario: 节点出口发出 node_end 生命周期事件

- **GIVEN** 某图节点正在执行
- **WHEN** 节点函数执行完成（出口，返回状态更新前）
- **THEN** 后端 SHALL 通过 custom 流发出 `{"type": "node_end", "node": <node_id>, "ts": <epoch_ms>, "duration_ms": <ms>}`
- **AND** duration_ms 为该节点真实执行耗时（出口 ts - 入口 ts），>= 0

#### Scenario: 全部图节点统一包裹计时

- **GIVEN** 5 层管线图构建
- **THEN** 全部 22 个图节点 SHALL 通过统一的计时装饰器包裹（在 add_node 注册处应用）
- **AND** 装饰器 SHALL NOT 改变节点的签名、返回值与业务逻辑

#### Scenario: 并行分析师时间戳归属正确

- **GIVEN** Layer I 的 4 个分析师经 Send 扇出并行执行
- **WHEN** 各分析师发出 node_start/node_end 生命周期事件
- **THEN** 每个事件的 node 字段 SHALL 正确对应该分析师节点名
- **AND** 各分析师的 ts 互不串扰

#### Scenario: node_start 事件附加入口时间戳

- **GIVEN** 节点的 custom node_start（真实入口）已先于 updates chunk 到达
- **WHEN** 后端为该节点发出 node_start 事件（updates chunk 首次出现时）
- **THEN** node_start 事件 SHALL 附加 `server_start_ts`（后端真实入口时间戳）
- **AND** 该字段 SHALL 透传至 SSE 事件供前端用于"当前节点已运行时长"

#### Scenario: node_end 到达时下发 node_timing 事件

- **GIVEN** 某节点的 custom node_end（真实出口 + duration）到达
- **WHEN** 该节点的 node_complete 可能已先于 node_end 发出（updates chunk 驱动）
- **THEN** 后端 SHALL 额外下发 `node_timing` SSE 事件，携带 `node_id`、`server_start_ts`、`server_end_ts`、`server_duration_ms`
- **AND** 前端 SHALL 用 node_timing 的真实耗时更新该节点的 durationMs（覆盖 updates 到达时刻的近似值）

#### Scenario: 快速节点计时真实

- **GIVEN** 某快速纯函数节点（如 check_cache）真实执行耗时 <1s
- **WHEN** 该节点完成
- **THEN** 前端节点计时 SHALL 显示基于 server_duration_ms 的真实耗时
- **AND** 真实耗时 <1s 时显示 "0:00" 属正确行为（区别于"恒为 0 的假象"）
