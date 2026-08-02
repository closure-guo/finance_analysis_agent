# Proposal: persist-full-session-timeline

## Why

切换会话或关闭页面后，深度分析的**思考内容、网络搜索、工具调用记录、深度分析管线时序记录**部分丢失，无法完整恢复。

根因不是恢复逻辑缺失，而是**持久化缺口**：前端渲染的四类会话数据中，三类根本没有结构化持久化到后端——

- **对话侧**：`chat_history[].thinking` 只存合并的思考字符串，`tool_calls` 与搜索的交错时序被「思考在前、工具在后」拍平（`buildTimelineFromHistory` 近似还原，时序失真）；网络搜索无独立存储，完全丢失。
- **管线侧**：各节点的思考/工具时序（前端 `nodeTimelines`）**从未写入后端**，`agent_process` 只存 Layer II-V 中间结论，切换后管线详细时序全部丢失。

用户期望：所有会话信息都结构化持久化，切换会话或关闭页面后应能**完整、按时序**恢复。

## What Changes

- **对话时序结构化持久化**：`chat_history` 的 assistant 条目新增 `agentTimeline` 字段（完整 TimelineItem 数组：思考/搜索/工具调用的交错时序），替代仅靠拍平 `thinking` 字符串的恢复。后端 `_ChatCollector` 在流式消费时构建结构化时序（复用与前端 `applyChatStreamEvent` 等价的语义），`append_chat` 一并写入。
- **管线时序持久化**：sessions 表新增 `pipeline_timelines` 列（JSON），按节点分组存 `{node: [TimelineItem]}`。管线运行中（fast path 的 PipelineRunner 与 ReAct 的 run_deep_analysis 工具）在节点事件时同步维护并写入，与现有 `pipeline_snapshot` 同节奏。
- **恢复原样重建**：前端 `selectSession` 恢复时，优先用持久化的 `agentTimeline` / `pipeline_timelines` 原样重建时序（不再走 `buildTimelineFromHistory` 拍平近似）；旧会话无新字段时回退现有近似逻辑，向后兼容。

## Capabilities

### New Capabilities

（无——本 change 是对现有会话恢复能力的补全，不引入新能力域。）

### Modified Capabilities

- `session-persistence`: 会话历史持久化需覆盖对话时序（agentTimeline）与管线时序（pipeline_timelines）的完整结构，不再仅存拍平的 thinking 字符串与中间结论。
- `frontend`: selectSession 恢复逻辑需优先使用持久化的结构化时序原样重建（对话 agentTimeline + 管线 nodeTimelines），旧数据回退近似恢复。

## Impact

- **后端**：`session_store.py`（pipeline_timelines 列迁移 + 读写；append_chat 支持 agentTimeline）、`api.py`（_ChatCollector 构建结构化时序）、`pipeline_runner.py` + `agent_factory.py`（管线节点事件时维护 pipeline_timelines）。
- **前端**：`types.ts`（ChatHistoryEntry.agentTimeline、SessionDetail.pipeline_timelines）、`App.tsx`（selectSession 恢复优先结构化时序）、`timeline.ts`（时序序列化/反序列化辅助）。
- **存储**：sessions 表新增 `pipeline_timelines` 列（幂等 ALTER TABLE）；chat_history assistant 条目新增 `agentTimeline` 字段（JSON，向后兼容——旧条目无该字段）。
- **测试**：后端时序持久化单测、前端结构化恢复单测、E2E 切换会话完整恢复用例（思考/搜索/工具/管线时序均可见）。
- **既有不回归**：report/chat_history 现有恢复、管线快照恢复（resume-pipeline-across-sessions）不回归。
