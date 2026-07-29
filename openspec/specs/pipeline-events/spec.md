# Pipeline Events Specification

## Purpose

定义深度分析管线的后台执行、断点恢复与进度快照持久化能力域。管线执行与 SSE 订阅解耦：客户端断开 SSE 连接（如切换会话）不中断管线执行，管线进度快照持久化到会话，使客户端切回会话时可恢复管线 UI。

## Requirements

### Requirement: 管线后台执行与断点恢复

系统 SHALL 使深度分析管线的执行与 SSE 订阅解耦：管线在独立后台任务中运行，客户端断开 SSE 连接（如切换会话）SHALL NOT 中断管线执行；管线进度快照 SHALL 持久化到会话，使客户端切回会话时可恢复管线 UI。

#### Scenario: SSE 断开后管线后台继续执行

- **GIVEN** 某会话的深度分析管线正在运行
- **WHEN** 客户端断开 SSE 连接（切换会话、关闭标签页）
- **THEN** 后端管线 SHALL 在后台任务中继续执行
- **AND** 管线完成后 SHALL 照常写入会话的报告与分析产物（report_markdown/agent_process/analyst_reports）
- **AND** 会话 status 在管线完成后 SHALL 更新为 completed

> **适用范围（design.md §8）**：该「SSE 断开后后台续跑到底」行为当前仅适用于 **fast path**（`/api/analyze` 带 `stock_code` 且无 `session_id` 的直传路径，由后端 PipelineRunner 后台线程保护）。ReAct 主链路（自然语言输入，前端从不传 `stock_code`）的 SSE 断开完整后台化为**后续 change**（design.md §8 第 2 层）。ReAct 路径当前能力为：快照在断开前持续写入、会话状态兜底（running/completed/failed），切回时前端通过快照 + 轮询恢复时间轴。

#### Scenario: 管线进度快照持久化

- **GIVEN** 管线正在后台运行
- **WHEN** 任一图节点完成
- **THEN** 系统 SHALL 将当前管线状态快照（layerTree 各节点 status/startedAt/durationMs、currentNodeId、progress、updatedAt）持久化到会话的 pipeline_snapshot
- **AND** 快照 SHALL 可序列化为 JSON 并反序列化还原分层时间轴

#### Scenario: 会话详情返回管线快照与运行状态

- **GIVEN** 某会话有进行中的或已完成的管线
- **WHEN** 客户端请求 GET /api/sessions/{id}
- **THEN** 响应 SHALL 包含会话 status（running/completed/failed）与 pipeline_snapshot（若存在）

#### Scenario: 重复启动幂等

- **GIVEN** 某会话的管线已在后台运行
- **WHEN** 因客户端重连/重试再次触发该会话的管线启动
- **THEN** 系统 SHALL NOT 重复启动管线，复用进行中的后台任务

#### Scenario: 后端重启后悬挂 running 会话处理

- **GIVEN** 后端进程重启前某会话 status=running（管线未持久化完成）
- **WHEN** 后端启动
- **THEN** 系统 SHALL 将无法恢复的 running 会话标记为 failed（MVP 策略）
- **AND** 客户端切回该会话时显示失败状态而非误认为仍在运行
