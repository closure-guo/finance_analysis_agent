# Design: persist-full-session-timeline

## Context

前端会话视图有四类动态时序数据，恢复链路存在持久化缺口（勘察结论）：

| 数据 | 前端载体 | 现有持久化 | 缺口 |
|------|---------|-----------|------|
| 对话思考 | `chat 消息.agentTimeline` | `chat_history[].thinking`（合并字符串） | 与搜索/工具的交错时序被拍平 |
| 网络搜索 | agentTimeline 的 search item | 无独立存储 | 完全丢失 |
| 工具调用 | agentTimeline 的 tool_call item | `chat_history[].tool_calls` | 与思考的交错时序被拍平 |
| 管线节点思考/工具 | `pipeline 消息.nodeTimelines` | 无（agent_process 仅存 Layer II-V 中间结论） | 完全丢失 |

现有恢复用 `buildTimelineFromHistory`「思考在前、工具在后」近似还原，时序失真；管线 `nodeTimelines` 从未持久化。本设计将四类数据全部结构化持久化，恢复时原样重建。

## Goals / Non-Goals

**Goals**
- 对话侧：assistant 消息的思考/搜索/工具调用按真实交错时序持久化并恢复。
- 管线侧：各节点思考/工具时序持久化并恢复。
- 向后兼容：旧会话（无新字段）回退现有近似恢复，不报错。
- 既有 resume-pipeline-across-sessions 的快照恢复、report/chat_history 恢复不回归。

**Non-Goals**
- 不改变 SSE 事件流与在线渲染逻辑（只增持久化与恢复，不动 `applyChatStreamEvent`/渲染组件）。
- 不持久化 thinking 的 token 级中间态（按时序条目的最终形态存即可）。
- 不重建旧会话已丢失的历史时序（仅新会话生效）。
- 不改管线后台化语义（resume change 已闭环）。

## Decisions

### D1. TimelineItem 为跨端共享的持久化单元

持久化结构直接复用前端 `TimelineItem` 联合类型（thinking/search/tool_call，见 `frontend/src/types.ts:313-321`），后端按同构 JSON 写入。避免再发明一套存储 schema，恢复时免转换。

- `thinking`: `{type, content, title?, done?}`
- `search`: `{type, query, results?, status}`
- `tool_call`: `{type, name, args, result?, done}`

### D2. 对话侧：后端构建结构化 agentTimeline

后端 `_ChatCollector`（api.py:834）当前只累积 `response/thinking/tool_calls`。扩展其在 `feed()` 中同时维护一个 `agentTimeline: list[dict]`，按与前端 `applyChatStreamEvent` 等价的语义构建（thinking 片段遇 search/tool 断开、tool_call 收口前段 thinking 等）。**为避免双端逻辑漂移，抽取共享语义**：前端 `timeline.ts` 的 `applyChatStreamEvent` 是事实标准，后端在 Python 侧实现其等价子集（appendThinkingToken/closeLastThinking/search/tool_call/chat_done 收口）。`append_chat` 新增可选 `agent_timeline` 参数，写入 `chat_history` 条目的 `agentTimeline` 字段。

备选（否决）：前端在 SSE 结束时把 agentTimeline POST 回后端——增加一次往返且依赖前端在线，断开即丢失；后端在流式消费时构建更可靠。

### D3. 管线侧：新增 pipeline_timelines 列，节点事件时维护

sessions 表新增 `pipeline_timelines TEXT`（JSON：`{node: [TimelineItem]}`）。管线两个执行路径（fast path 的 `PipelineRunner._run`、ReAct 的 `run_deep_analysis` 工具）在处理 thinking/search/tool 事件时，按节点分组维护并写入，节奏与现有 `pipeline_snapshot` 一致（每节点事件写一次）。复用 `pipeline_runner` 既有的事件解析，新增 `update_pipeline_timelines(session_id, timelines)`。

- thinking_token 带 `node` 字段 → 归入该节点的 timeline（等价前端 `applyPipelineThinkingToken`）。
- 节点完成时收口该节点末段 thinking（等价 `applyPipelineNodeComplete`）。

### D4. 恢复：优先结构化，旧数据回退近似

`selectSession`：
- chat 消息：`h.agentTimeline` 存在 → 直接作为 `agentTimeline`（反序列化）；否则回退 `buildTimelineFromHistory(h.thinking, h.tool_calls)`。
- pipeline 消息：`data.pipeline_timelines` 存在 → 反序列化为 `nodeTimelines`；否则缺省（时间轴树仍由 pipeline_snapshot 恢复，节点时序为空）。

前端 `timeline.ts` 新增 `serializeTimeline`/`deserializeTimeline`（防御非法 JSON 回退空数组）。

## Risks / Trade-offs

- **双端时序语义漂移** → 后端 Python 版与前端 `timeline.ts` 必须逐项等价；用共享测试夹具（同一事件序列，两端产出一致 timeline）防漂移，E2E 验证真实链路。
- **存储体积增长**（思考全文 + 搜索结果）→ 单会话量级 KB~几十 KB，SQLite 可承受；搜索结果 content 已是截断摘要。
- **写入频率**（每节点事件一次）→ 与 pipeline_snapshot 同节奏，本地 SQLite 开销可忽略。
- **旧数据兼容** → 恢复逻辑对缺失字段回退近似，迁移幂等（ALTER TABLE suppress OperationalError）。

## Migration Plan

1. `session_store.init_db()` 迁移列表追加 `pipeline_timelines` 列（幂等）。
2. `append_chat` 新增 `agent_timeline` 可选参数（默认 None，旧调用方不受影响）。
3. 后端 collector/管线写入 + 前端恢复，分段落地，每段独立测试。
4. 回滚：新字段/新列均为可选，回滚代码后旧逻辑自然生效（新列残留无影响）。

## Open Questions

- 无（持久化范围与存储位置已与用户确认：全量结构化 + 独立列）。
