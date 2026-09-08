# Proposal: fix-stream-event-routing

## Why

深度模式 ReAct 澄清阶段（search_stock/web_search 工具调用 + 思考流式输出 + 文本回复）的**实时流式渲染**出现两类错乱：

1. **思考 UI 错位**：澄清阶段的思考横幅从对话流消息中消失、出现在管线卡片里，或思考横幅里混入回复正文。
2. **回复格式错乱**：DSML 触发时回复正文换行/列表结构丢失（列表挤成一段）。

**刷新页面后从 chat_history 重建即恢复正常**——因为重建路径从后端落库的 `agentTimeline` 反序列化（无路由判断），而实时路径按「管线消息是否存在」做静态事件路由，与事件真实归属不一致。实时路径的 bug 使用户在每次澄清阶段都看到错乱 UI，只有刷新才能看到正确结构。

## What Changes

- 前端 SSE 事件分发（`startAnalysis` 与 `resumeStream` 两处镜像逻辑）中，`thinking_token` 的路由条件从「`pipelineMsgRef.current != null`」改为「事件归属」：仅当事件携带管线节点标识（`event.node`）时才路由进管线 UI（`handleSSEEvent`），否则一律进对话流（`handleChatStreamEvent`）。
- `thinking_replace` / `thinking_to_answer` 不再因 `pipelineMsgRef.current != null` 被静默丢弃——它们作用于对话流消息末尾 thinking item（DSML 清理、流末切割），应始终路由到对话流。
- `pipelineMsgRef` 生命周期收口：管线完成（report_ready / done）后置 null，避免后续轮次的澄清思考被路由到已完成的管线消息。

非目标（Out of scope）：
- 不改变后端 `_ChatCollector.feed` 落库逻辑（已正确，是重建路径正确的原因）。
- 不改变 `applyChatStreamEvent` 纯函数本身（逻辑正确，问题在路由层）。
- DSML 补发切片的语义边界对齐（次级优化，若本次路由修复后格式错乱消失则不做）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 修改「Clarification Conversation Flow」「Conversation Stream Common Events」相关行为——澄清阶段的 thinking/search/tool_call 事件归属判定从「全局管线 UI 状态」改为「事件自身 node 标识」。现有 spec 的 `#### Scenario: 澄清阶段走对话流`、`#### Scenario: 思考过程在澄清阶段走对话流` 已规定澄清事件应写入对话流 `agentTimeline`，但实时实现在管线消息存在时违反该契约。本变更使实时行为与 spec 契约对齐。

## Impact

- **前端**：`frontend/src/App.tsx`（`startAnalysis` SSE 循环、`resumeStream` 事件分发、`pipelineMsgRef` 生命周期）。
- **后端**：无改动。
- **测试**：新增前端测试（管线消息存在时澄清 thinking 仍进对话流、thinking_replace 不被丢弃、report_ready 后 pipelineMsgRef 置 null）；交互行为变更需人工验证落 `tests/validation/`。
- **E2E**：属交互行为变更，需 E2E 门禁（真实前后端，验证澄清阶段流式渲染不错位）。
