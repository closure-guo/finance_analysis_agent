# Design: fix-stream-event-routing

## Context

前端 `frontend/src/App.tsx` 的深度模式 SSE 事件分发存在路由 bug。`startAnalysis`（App.tsx:933-958）与 `resumeStream`（App.tsx:1708-1715 镜像）中：

- `thinking_token` 按 `pipelineMsgRef.current != null` 路由：管线消息存在时进 `handleSSEEvent`（写入 `pipelineMsg.nodeTimelines[event.node || '']`），否则进 `handleChatStreamEvent`（写入对话流 `agentTimeline`）。
- `thinking_replace` / `thinking_to_answer` 在 `pipelineMsgRef.current != null` 时被静默丢弃。

`pipelineMsgRef.current` 在 `run_deep_analysis` tool_call 到达后创建，**且存活到会话切换/新建才清空**（report_ready 不清）。澄清阶段的思考事件大多**不带 `node` 字段**（后端 `agent_factory.py:959-962` 仅有 node metadata 才透传），于是被归入 `nodeTimelines['']`，渲染到管线卡片，从对话流消失 → 思考错位；`thinking_replace` 被丢弃 → DSML 清理不生效 → 思考横幅残留回复前缀 + 正文格式错乱。

后端 `_ChatCollector.feed` 不看路由，无差别把全部对话流事件灌进 `agentTimeline` 落库，故刷新重建（deserializeTimeline）结构正确。即「刷新后正常」正是绕过了实时路由 bug。

## Goals / Non-Goals

**Goals:**
- 澄清/对话流事件按事件自身 `node` 归属路由，与后端 `_ChatCollector` 落库行为对齐。
- thinking_replace / thinking_to_answer 不被管线状态丢弃。
- 管线完成后 pipelineMsgRef 收口，不影响后续轮次。

**Non-Goals:**
- 不改后端 `_ChatCollector` / `timeline_builder`（已正确）。
- 不改 `applyChatStreamEvent` 纯函数（逻辑正确）。
- DSML 补发切片语义边界对齐（次级，路由修复后若格式恢复则不做）。

## Decisions

### D1: thinking_token 路由条件改为「事件携带 node 字段」

`thinking_token` 仅当 `event.node` 非空时进 `handleSSEEvent`（管线节点时序），否则一律 `handleChatStreamEvent`（对话流）。这与后端 `agent_factory.py:959-962` 的透传逻辑天然对齐：管线节点思考带 `node`，澄清思考不带。

- **备选**：按 appState 路由（analyzing 时全进管线）——但 analyzing 期间 Agent 仍可能发澄清思考（多轮、追问后），同样错位。按 `node` 归属是唯一与事件语义一致的条件。

### D2: thinking_replace / thinking_to_answer 无条件路由到对话流

这两类事件作用于对话流消息末尾 thinking item（DSML 清理、流末切割），管线侧无对应概念。移除 `pipelineMsgRef` 判断，始终 `handleChatStreamEvent`。

### D3: pipelineMsgRef 在 report_ready / done 时置 null

管线完成后置 null，后续轮次澄清思考不再被路由到已完成的管线消息。需在 `report_ready` 处理与 `done` 终态处理处补充置 null，同时保留 pipelineMsg 在 messages 中的展示（仅清 ref，不删消息）。

### D4: startAnalysis 与 resumeStream 两处同步修改

两处事件分发逻辑镜像（实时 + 断线恢复），必须同步修改，否则刷新恢复后仍错位。

## Risks / Trade-offs

- [管线节点思考事件 `node` 字段缺失时被误路由到对话流] → 后端管线节点 thinking 经 `run_deep_analysis` 内 `_put_event(StreamEvent.think(..., metadata={"node": node}))` 必带 node；fast path PipelineRunner 的 node_start/node_complete 也带 node。澄清思考才不带。路由边界清晰。
- [pipelineMsgRef 提前置 null 导致管线后续事件无处写入] → report_ready 是管线最后一个内容事件，其后仅 done 终态；done 不依赖 pipelineMsgRef。安全。

## Migration Plan

纯前端改动，无后端迁移、无数据迁移。回滚：还原路由条件即可。

## Open Questions

（无）
