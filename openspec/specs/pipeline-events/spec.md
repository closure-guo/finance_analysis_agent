# Pipeline Events Specification

## Purpose

定义深度分析管线的后台执行、断点恢复与进度快照持久化能力域。管线执行与 SSE 订阅解耦：客户端断开 SSE 连接（如切换会话）不中断管线执行，管线进度快照持久化到会话，使客户端切回会话时可恢复管线 UI。该能力同时适用于 fast path 和 ReAct 路径。

## Requirements

### Requirement: 管线后台执行与断点恢复

系统 SHALL 使深度分析管线的执行与 SSE 订阅解耦：管线在独立后台任务中运行，客户端断开 SSE 连接（如切换会话）SHALL NOT 中断管线执行；管线进度快照 SHALL 持久化到会话，使客户端切回会话时可恢复管线 UI。该能力 SHALL 同时适用于 fast path（`/api/analyze` 带 `stock_code` 直传路径）和 ReAct 路径（自然语言输入，Agent 通过 `run_deep_analysis` 工具触发管线）。

#### Scenario: SSE 断开后管线后台继续执行

- **GIVEN** 某会话的深度分析管线正在运行（无论 fast path 还是 ReAct 路径）
- **WHEN** 客户端断开 SSE 连接（切换会话、关闭标签页）
- **THEN** 后端管线 SHALL 在后台任务中继续执行
- **AND** 管线完成后 SHALL 照常写入会话的报告与分析产物（report_markdown/agent_process/analyst_reports）
- **AND** 会话 status 在管线完成后 SHALL 更新为 completed

#### Scenario: ReAct 路径管线后台化

- **GIVEN** 用户通过自然语言输入触发深度分析，Agent 调用 `run_deep_analysis` 工具
- **WHEN** 客户端在管线执行期间断开 SSE 连接
- **THEN** `run_deep_analysis` 工具内的 `graph.stream` SHALL 在后台任务中继续执行
- **AND** 管线进度快照 SHALL 持续持久化到会话的 pipeline_snapshot
- **AND** 管线完成后 SHALL 将最终报告写入会话存储
- **AND** 会话 status SHALL 更新为 completed
- **AND** 客户端切回该会话时 SHALL 通过快照 + 轮询恢复管线 UI 并展示最终报告

#### Scenario: 管线进度快照持久化

- **GIVEN** 管线正在后台运行
- **WHEN** 任一图节点完成
- **THEN** 系统 SHALL 将当前管线状态快照（layerTree 各节点 status/startedAt/durationMs、currentNodeId、progress、updatedAt）持久化到会话的 pipeline_snapshot
- **AND** 快照 SHALL 可序列化为 JSON 并反序列化还原分层时间轴

#### Scenario: 会话详情返回管线快照与运行状态

- **GIVEN** 某会话有进行中的或已完成的管线
- **WHEN** 客户端请求 GET /api/sessions/{id}
- **THEN** 响应 SHALL 包含会话 status（running/completed/failed）与 pipeline_snapshot（若存在）
- **AND** 若 status 为 failed，响应 SHALL 包含 failure_reason 字段描述中断原因

#### Scenario: 重复启动幂等

- **GIVEN** 某会话的管线已在后台运行
- **WHEN** 因客户端重连/重试再次触发该会话的管线启动
- **THEN** 系统 SHALL NOT 重复启动管线，复用进行中的后台任务

#### Scenario: 后端重启后悬挂 running 会话处理

- **GIVEN** 后端进程重启前某会话 status=running（管线未持久化完成）
- **WHEN** 后端启动
- **THEN** 系统 SHALL 将无法恢复的 running 会话标记为 failed（MVP 策略）
- **AND** SHALL 在 failure_reason 中记录"后端重启，管线无法恢复"
- **AND** 客户端切回该会话时显示失败状态而非误认为仍在运行

### Requirement: 管线超时与中断检测

系统 SHALL 对深度分析管线实施全局超时机制：管线启动后超过最大执行时间未完成时，系统 SHALL 将会话标记为 failed 并记录超时原因。会话 status 更新为 failed 时 SHALL 持久化 `failure_reason` 字段，使客户端能展示具体中断原因而非笼统的"可能已中断"。

#### Scenario: 管线全局超时

- **GIVEN** 某会话的深度分析管线已启动并在后台运行
- **WHEN** 管线执行时间超过配置的最大执行时间（默认 10 分钟）
- **THEN** 系统 SHALL 终止管线执行
- **AND** SHALL 将会话 status 更新为 failed
- **AND** SHALL 在 failure_reason 中记录"管线执行超时"

#### Scenario: 管线异常中断原因持久化

- **GIVEN** 管线执行过程中发生异常（数据拉取失败、LLM 调用失败、节点异常等）
- **WHEN** 异常导致管线中止
- **THEN** 系统 SHALL 将会话 status 更新为 failed
- **AND** SHALL 在 failure_reason 中记录异常类型与摘要信息
- **AND** 客户端切回该会话时 SHALL 通过 GET /api/sessions/{id} 获取 failure_reason 并展示

#### Scenario: 前端轮询展示中断原因

- **GIVEN** 客户端切回一个 status=failed 的会话
- **WHEN** 前端通过轮询获取到会话详情
- **THEN** 前端 SHALL 展示 failure_reason 中的具体中断原因
- **AND** SHALL NOT 仅显示笼统的"管线可能已中断"

### Requirement: LLM 调用错误传播

系统 SHALL 确保 LLM 调用失败时正确传播异常而非静默吞没：`chat_stream` 在重试耗尽后 SHALL raise 异常，使 Agent 主循环能捕获并产生 ERROR 事件，而非将错误文本作为正常回复 yield。

#### Scenario: LLM 重试耗尽后 raise 异常

- **GIVEN** LLM 调用经过最大重试次数后仍然失败
- **WHEN** `chat_stream` 的最后一次重试抛出异常
- **THEN** `chat_stream` SHALL raise 该异常（而非 yield 包含错误文本的 LLMResponse）
- **AND** Agent 主循环 SHALL 捕获该异常并 yield ERROR 事件
- **AND** 管线 SHALL 将会话 status 更新为 failed 并记录 failure_reason

#### Scenario: LLM 错误不产生静默失败

- **GIVEN** Agent 正在执行深度分析管线
- **WHEN** 某个节点的 LLM 调用失败且重试耗尽
- **THEN** 系统 SHALL NOT 将错误文本作为 LLM 的正常最终回复处理
- **AND** SHALL NOT 在未执行分析的情况下静默结束管线

### Requirement: SSE 流心跳保护

系统 SHALL 为所有 SSE 流（包括 fast path 和 ReAct 路径）发送心跳注释，防止代理/浏览器因空闲超时断开连接。心跳 SHALL 在管线长时间无事件输出时周期性发送。

#### Scenario: ReAct 路径 SSE 心跳

- **GIVEN** 用户通过自然语言触发深度分析，SSE 流已建立
- **WHEN** 管线执行期间连续 N 秒（默认 15 秒）无事件输出
- **THEN** 系统 SHALL 发送 SSE 心跳注释（`: heartbeat\n\n`）
- **AND** 心跳 SHALL NOT 干扰正常事件流的解析

#### Scenario: fast path SSE 心跳（保持现有行为）

- **GIVEN** 用户通过 fast path 触发深度分析
- **WHEN** 管线执行期间 SSE 事件队列空闲
- **THEN** 系统 SHALL 继续发送心跳注释（与当前行为一致）
