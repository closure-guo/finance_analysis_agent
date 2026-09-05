# Proposal: add-user-feedback

## Why

消息操作条已加入「点赞/点踩」（本地 toggle 交互态），但**未接后端**：点击仅改变前端高亮，反馈数据丢失。接入 Langfuse 后，用户的显式反馈可落在产生该消息的 trace 上（`create_score`），与 LLM 调用、思考、工具链路关联——这是评估体系「人工对齐」最直接的信号源（judge 校准、偏好数据采集都靠它）。

## What Changes

- **trace_id 管道打通**：chat 运行（quick AG-UI 与 deep ReAct）完成时把该次运行的 `langfuse_trace_id` 放进 SSE 终态事件；前端把它存到 chat UIMessage，经 adapter metadata 透传给消息操作条
- **后端反馈端点**：`POST /api/feedback`（`{ trace_id, value }`，value ∈ like/dislike）→ `langfuse.create_score(name="user_feedback", value, trace_id)`；旁路铁律（失败仅 WARN 不阻断），trace 不存在/过期按 Score 上报语义容错
- **前端接线**：点赞/点踩点击 → 调反馈端点（乐观更新选中态 + 已提交标记）；无 trace_id 时仅本地 toggle（降级，不报错）
- 不改消息本身结构（trace_id 作为可选字段，旧数据无 trace_id 时优雅降级）

## Capabilities

### New Capabilities

- `user-feedback`: 用户对 agent 输出的显式反馈（点赞/点踩）落到产生该输出的 Langfuse trace 上

### Modified Capabilities

（无——trace_id 管道是内部实现细节，不改变既有 capability 行为契约；如接入后需调整 trace-observability 的断言再补 MODIFIED）

## Impact

- **后端**：api.py 新增 `POST /api/feedback`；quick（AG-UI `/api/agui/quick`）与 deep（run_deep_analysis 工具 / agent_factory）的 SSE 终态事件注入 `langfuse_trace_id`
- **前端**：types.ts（UIMessage 加 `langfuse_trace_id?`）、reducer（chat_done 存 trace_id）、adapter（metadata.custom 透传）、AnalysisThread MessageActions（点赞/点踩调端点）
- **测试**：端点单测（mock Langfuse、非法 value 422、无 trace 容错）；reducer/adapter/MessageActions 单测；E2E 说明——stub 无真实 Langfuse，端到端 trace 落库需 @live/本地真实运行验证
- **风险**：`get_current_trace_id()` 在 SSE 处理器上下文是否可用需实证；不同模式（quick/deep）trace 归属粒度（一次运行一个 trace）
