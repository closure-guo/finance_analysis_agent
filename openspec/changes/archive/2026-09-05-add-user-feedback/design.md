# Design: add-user-feedback

## Context

消息操作条已实现四个图标按钮（复制/重试/点赞/点踩），点赞/点踩为纯本地 toggle。接入 Langfuse 需要把「产生该消息的运行 trace」关联到反馈上。现状：SSE 事件不带 trace_id、UIMessage 无此字段、后端无 feedback 端点。

## Goals / Non-Goals

**Goals:** 点赞/点踩 → `create_score(trace_id, user_feedback, 1/0)`；trace_id 经 SSE → 消息 → adapter 透传；历史消息无 trace_id 优雅降级。
**Non-Goals:** 不做取消上报（再点取消仅本地）；不做标注队列/人工审核流（那是评估体系后续）；不改 Langfuse 侧 UI。

## Decisions

**决策 1：反馈端点旁路铁律，与决策 Score 上报同语义。**
`POST /api/feedback` 调 `langfuse.create_score`，任何异常记 WARN 返回成功（前端不感知后端失败）；`trace_id`/`value` 校验失败返回 422。复用 `get_langfuse()` 单例。

**决策 2：trace_id 在 SSE 终态事件注入，quick 与 deep 两条路径分别处理。**
- quick（AG-UI `/api/agui/quick`）：在流式循环中捕获 `client.get_current_trace_id()`（OTel 上下文在生成观测内活跃），在 `run_finished` 事件注入。
- deep（run_deep_analysis 工具）：在工具完成分支用同一方式捕获，注入终态事件。
- 风险：`get_current_trace_id()` 在处理器上下文是否可用需实证（备选：在生成观测回调里捕获）。实证失败则退回「session 级最近 trace」降级方案，spec 已允许降级语义。

**决策 3：前端 trace_id 作为 UIMessage 可选字段。**
reducer 在 chat_done 时把事件里的 `langfuse_trace_id` 存到 chat 消息；adapter 在 metadata.custom 透传；MessageActions 读 trace_id，有点赞/点踩才调端点，无则本地 toggle。旧消息（重建/历史）无字段 → 自动降级。

**决策 4：value 映射 like=1 / dislike=0（BOOLEAN）。**
与决策 Score 的 BOOLEAN 风格一致；后续若需区分强度再升 NUMERIC。

## Risks / Trade-offs

- [get_current_trace_id 上下文不可用] → 实证；失败退 session 级降级（spec 已覆盖降级场景）
- [多次运行同消息归属] → deep 工具一次运行一个 trace，取工具运行上下文；边界为「最后一次生成该消息的运行」
- [评分重复（用户多次切换点赞/点踩）] → 首版每次点击都上报（Langfuse score 允许同名多条），取消不上报；如需幂等再引入 feedback_log 表

## Migration Plan

纯增量：新端点 + SSE 字段 + 前端可选字段。旧数据无 trace_id 自动降级，无迁移。

## Open Questions

- get_current_trace_id 的上下文可用性（实现时实证）
- 是否需要 feedback_log 表防重复上报（首版不做，Langfuse score 天然多值）
