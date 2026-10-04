# Delta for pipeline-events

## MODIFIED Requirements

### Requirement: 管线超时与中断检测

系统 SHALL 对深度分析管线实施全局超时机制：管线启动后超过最大执行时间未完成时，系统 SHALL 将会话标记为 failed 并记录超时原因。会话 status 更新为 failed 时 SHALL 持久化 `failure_reason` 字段，使客户端能展示具体中断原因而非笼统的"可能已中断"。默认最大执行时间从 10 分钟上调为 40 分钟，以匹配 LLM 端点的生成耗时方差（实测单节点 3.7~15.7 分钟，R1+R2 合法双轮最坏约 32 分钟）。
(Previously: 默认最大执行时间 10 分钟)

超时判定 SHALL 基于管线（图）的真实完成状态而非事件流的排空进度：预算耗尽时，若图已完成（交付物已生成或图流已结束），系统 SHALL 按完成路径处置（交付成果、正常终态），MUST NOT 判超时失败——事件排空延迟（明细洪峰滞后）不构成超时。仅当图自身在预算内确实未完成时才判超时。

#### Scenario: 管线全局超时

- GIVEN 某会话的深度分析管线已启动并在后台运行
- WHEN 管线执行时间超过配置的最大执行时间（默认 40 分钟）
- THEN 系统 SHALL 终止管线执行
- AND SHALL 将会话 status 更新为 failed
- AND SHALL 在 failure_reason 中记录"管线执行超时"

#### Scenario: 预算耗尽但管线已完成不得判超时

- GIVEN 深度分析管线在预算内已完成并生成报告，但事件流排空存在分钟级滞后（明细洪峰）
- WHEN 全局预算（如 2400 秒）在事件排空完成前耗尽
- THEN 系统 SHALL 按完成路径处置：交付已生成的报告、正常终态、会话状态流转 completed
- AND MUST NOT 判超时失败，MUST NOT 生成"管线执行超时"的失败语义
- AND 缓冲的明细事件 SHALL 允许压缩丢弃以使终态有界送达（见 session-streaming「终态事件优先送达」）

#### Scenario: 环境变量覆盖默认

- GIVEN 部署方设置了 PIPELINE_TIMEOUT_SECONDS 环境变量（如 "600"）
- WHEN 管线执行时间超过该环境变量配置的值
- THEN 超时判定 SHALL 以环境变量配置为准（默认值仅作未配置时兜底）

#### Scenario: 管线异常中断原因持久化

- GIVEN 管线执行过程中发生异常（数据拉取失败、LLM 调用失败、节点异常等）
- WHEN 异常导致管线中止
- THEN 系统 SHALL 将会话 status 更新为 failed
- AND SHALL 在 failure_reason 中记录异常类型与摘要信息
- AND 客户端切回该会话时 SHALL 通过 GET /api/sessions/{id} 获取 failure_reason 并展示

#### Scenario: 前端轮询展示中断原因

- **GIVEN** 客户端切回一个 status=failed 的会话
- **WHEN** 前端通过轮询获取到会话详情
- **THEN** 前端 SHALL 展示 failure_reason 中的具体中断原因
- **AND** SHALL NOT 仅显示笼统的"管线可能已中断"
