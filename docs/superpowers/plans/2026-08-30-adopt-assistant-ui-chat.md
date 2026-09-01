# adopt-assistant-ui-chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 深度/历史消息区整体迁移到 assistant-ui Thread（ExternalStore 模式），输入区换 Composer；后端 SSE 协议与 streamStore 语义不变。

**Architecture:** streamStore 仍是事件归约/续传/重建的唯一事实源（reduce 已有逐事件测试）。新增两层：
1. `src/chat/adapter.ts` — 纯函数翻译层 `uiMessageToThreadMessageLike(UIMessage) → ThreadMessageLike`，把 UIMessage 的各字段（agentTimeline/chatResponse/pipeline/report/...）映射为 assistant-ui 消息部件（text / reasoning / tool-call / data-*）。
2. `src/chat/AnalysisThread.tsx` — `useExternalStoreRuntime` 接线（convertMessage=translate、isRunning=store phase、onNew=submit、onCancel=cancel）+ Thread 视图（Viewport autoScroll + 自定义部件渲染）。

**Tech Stack:** @assistant-ui/react 0.15.17（useExternalStoreRuntime / ThreadPrimitive / ComposerPrimitive / MessagePrimitive.Parts data.by_name）。

## Global Constraints

- 后端 SSE 事件协议、session-store（streamStore/reduce/rebuild/resume）语义零修改
- 既有前端测试 SHALL 无修改通过（仅允许更新选择器）；保留测试 DOM 契约：
  `send-button`、`stream-output`（chat 消息整体容器，含横幅+正文）、`stream-status`、`pipeline-timeline`、`report-name-banner`、`conversation-files-banner`、ChatInputBar/EmptyState 独立渲染可用
- 显式设置 message status（streaming→running / 否则 complete），避免 assistant-ui 把无 result 的 tool-call 判为 requires-action
- 工具调用 loading 语义经 part.artifact.done 传递（result 缺省不触发 runtime 状态机）

## SSE 事件 → 消息部件映射表（Task 2.1 产物）

| SSE 事件 | reduce 归宿 (UIMessage) | ThreadMessage 部件 |
|---|---|---|
| 提交 / user_message | user 消息 | user text |
| chat_token / chat_done | chat.chatResponse + streaming | assistant text（status running/complete） |
| thinking_token（无 node）/ thinking_replace / thinking_to_answer | agentTimeline thinking item | reasoning part |
| tool_call（非搜索、非 run_deep_analysis）/ tool_result / stock_resolved(澄清) / tool_result(search_stock) | agentTimeline tool_call item | tool-call part（toolName/argsText/result/artifact.done） |
| search_start / search_result / search_error | agentTimeline search item | data-search part |
| tool_call(run_deep_analysis) / parsing / resolved / analysis_start / node_start / node_timing / node_complete / thinking_token(node) | pipeline 消息 | data-pipeline part |
| report_chunk / report_ready | report 消息 | data-report part |
| awaiting_input / done / interrupted | phase 转换 + 消息收口 | 消息 status（不产生新部件） |
| error | error 消息 / pipeline 消息 | data-error part / data-pipeline part |
| system | system 消息 | data-system part |
| session_created | store 层绑定（无 UI 形态） | 不产生部件 |

未知事件：reduce 的 default 分支已忽略（forward-compatible），adapter 不再单独处理。

## Tasks

### Task 1: adapter 纯函数 + 逐事件类型单测（TDD）
- Files: Create `frontend/src/chat/adapter.ts`; Test `frontend/src/test/chat/adapter.test.ts`
- 测试策略：每个 SSE 事件类型构造事件序列 → `reduce()`（streamStore）→ `translateMessage()` → 断言部件结构与映射表一致；未知事件安全忽略
- interfaces: Produces `uiMessageToThreadMessageLike(msg: UIMessage): ThreadMessageLike`、`translateMessages(msgs: UIMessage[]): ThreadMessageLike[]`

### Task 2: AnalysisThread 组件（runtime + 视图 + 部件）
- Files: Create `frontend/src/chat/AnalysisThread.tsx`
- `AnalysisRuntimeProvider`：useExternalStoreRuntime({ convertMessage: translate, isRunning, onNew, onCancel })
- `ThreadMessages`：ThreadPrimitive.Viewport(autoScroll) + Messages；AssistantMessage 用 useAuiState 读 metadata.custom.kind 决定 `stream-output`/管线/报告包裹形态；部件渲染映射：
  - Reasoning → ThinkingBanner（embedded，title=extractThinkingTitle(content)）
  - tools.Fallback → ToolCallBanner（单条目，entry 从 part 重建，streaming=artifact.done!==true）
  - data.by_name: pipeline→PipelineCard、report→ReportCard、search→SearchBanner、system→SystemBanner、error→ErrorBanner
- Task 4.1 一并完成：PipelineCard/ReportCard（内含 ECharts/导出所需 filePaths）经 data 部件原样挂载，能力不丢

### Task 3: App 接线 + Composer 输入区
- Modify `frontend/src/App.tsx`、ChatInputBar（插槽化）
- 消息列表块（MessageRenderer 遍历 + 横幅）→ AnalysisThread 内渲染；导出横幅置于 Viewport 尾部（保持现有位置）
- ChatInputBar 保持独立可渲染（默认受控插槽，dropdownOutsideClick 测试不变）；新增 composer 插槽（ComposerPrimitive.Input/Send/Cancel），App 内使用：
  - data-testid 保留：send-button（Send）、stream-status
  - onNew → mode==='quick' ? quickChat : startAnalysis（各自守卫+toast 语义不变）
  - onCancel → stopGeneration；isRunning = deepRunning || quickRunning
- 运行中拦截迁移至 runtime 状态判定（Composer 发送键变停止），onNew 内保留 toast 兜底

### Task 4: 验证
- `npm test` 全绿；`tsc -b`、eslint 通过
- 人工验证（浏览器）三模式/追问/停止/运行中拦截 → tests/validation/
- E2E 门禁：e2e 基建未落地（P1-P4 未建），如实记录为未完成项
