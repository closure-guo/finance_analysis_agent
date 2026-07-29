# Delta Spec: frontend（resume-pipeline-across-sessions）

## ADDED Requirements

### Requirement: 跨会话恢复管线 UI

系统 SHALL 在用户切换会话时恢复目标会话的管线 UI 状态：运行中的管线恢复实时分层时间轴，已完成的管线恢复报告与静态分层时间轴。切换离开运行中的深度管线会话时 SHALL NOT 中断该管线（由后端后台续跑）。

#### Scenario: 切回运行中的管线会话恢复实时时间轴

- **GIVEN** 某深度分析会话的管线正在后台运行（status=running 且有 pipeline_snapshot）
- **WHEN** 用户切换到该会话
- **THEN** 前端 SHALL 从 pipeline_snapshot 重建分层时间轴（各节点 status/耗时）
- **AND** 当前运行节点 SHALL 正确高亮，其已运行时长基于 server_start_ts 实时递增
- **AND** 前端 SHALL 轮询会话快照以更新节点完成进度，直至 status 变 completed

#### Scenario: 切回已完成的管线会话恢复报告与静态时间轴

- **GIVEN** 某会话的管线已完成（status=completed）
- **WHEN** 用户切换到该会话
- **THEN** 前端 SHALL 显示报告消息（report）与已完成的静态分层时间轴
- **AND** 静态时间轴各节点 SHALL 显示真实耗时与摘要（供回看）
- **AND** 前端 SHALL NOT 继续轮询该会话快照

#### Scenario: 切换离开运行中的深度管线不中断

- **GIVEN** 某深度分析会话的管线正在运行
- **WHEN** 用户切换到其他会话
- **THEN** 前端 abortStreaming 仅断开 SSE 订阅，SHALL NOT 中断后端管线执行
- **AND** 管线在后台继续，切回时可恢复

#### Scenario: 切回失败的管线会话显示失败状态

- **GIVEN** 某会话的管线已失败（status=failed，含后端重启悬挂的 running 被标记）
- **WHEN** 用户切换到该会话
- **THEN** 前端 SHALL 显示分析失败状态而非误认为仍在运行

> **MVP 决策**：MVP 阶段 failed 分支不专门处理 UI（回退到现有 report/chat_history 恢复逻辑），失败态 UI 为后续改进。

#### Scenario: 快速模式会话切换行为不变

- **GIVEN** 用户从快速模式（chat）会话切换离开
- **WHEN** 该会话无深度管线
- **THEN** 前端维持现有 abortStreaming 行为（快速模式流无恢复价值）

## MODIFIED Requirements

### Requirement: 会话状态管理

前端 `selectSession` SHALL 无条件调用 `abortStreaming()`--该调用仅断开 SSE 订阅，不影响后端管线执行。深度管线后台续跑由后端保护：fast path 由 PipelineRunner 后台线程保护，ReAct 路径由快照回调保护（design.md §8）。`selectSession` SHALL 按目标会话的 status 与 pipeline_snapshot 决定恢复管线 UI、报告、或仅对话历史。

> **简化决策（plan Task 5）**：原设计拟按会话类型条件化 abort（深度管线会话不 abort），实现中简化为无条件 abort--前端 abort 仅断开 SSE 订阅、不中断后端管线，故无需区分会话类型即可保证后台续跑。

#### Scenario: selectSession 按会话状态分发恢复逻辑

- **GIVEN** 用户点击切换到某会话
- **WHEN** 前端加载该会话详情
- **THEN** 系统 SHALL 根据 status 恢复：running+snapshot -> 实时管线时间轴；completed -> 报告+静态时间轴；failed -> 失败状态；无管线 -> 仅对话历史
- **AND** selectSession SHALL 无条件 abortStreaming（仅断开 SSE 订阅，不影响后端管线）
