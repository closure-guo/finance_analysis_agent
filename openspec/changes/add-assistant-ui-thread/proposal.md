# Proposal: add-assistant-ui-thread

## Why

1. **流式渲染协议债务**：现有 SSE 事件契约完全手搓（`streamStore/reduce.ts` 承载全部事件分支），事件路由错位、seq 丢失、切换竞态等 bug 族（fix-stream-event-routing、concurrent-subscription-seq-loss、select-session-stale-guard）均源于自研协议缺乏标准语义。
2. **assistant-ui 接入的前置已就绪**：`refactor-ui-design-system` 已入仓 shadcn 令牌与组件原语，assistant-ui（基于 shadcn/Radix 生态）具备了接入条件；AG-UI 协议是 assistant-ui 生态的配套 agent 协议，且有 LangGraph 官方适配层——我们后端正是 LangGraph。
3. **快速模式是最低风险的切入点**：quick 模式对话是单 run、无管线时间线的简单流式场景，适合作为 AG-UI + assistant-ui 的 PoC；管线时间线（5 层辩论等重领域事件）继续走现有通道，避免一次性重写。

## What Changes

- **后端 AG-UI 端点**：新增 `POST /api/agui/quick`（AG-UI RunAgentInput → SSE 事件流），用 AG-UI 官方 LangGraph 适配层包装 quick 模式 graph，输出标准 AG-UI 事件（TEXT_MESSAGE_*、RUN_* 等）；对话持久化沿用现有 session_store。
- **前端 assistant-ui 渲染**：quick 模式消息流改用 assistant-ui 的 Thread 组件 + `@ag-ui/client` runtime 渲染，替换该场景下的手写 ReactMarkdown 流式渲染；视觉复用 refactor-ui-design-system 的令牌与组件。
- **双轨共存**：深度模式与管线时间线完全不受影响，继续走现有 `/api/stream` SSE + streamStore 通道；quick 模式历史恢复（刷新/切回）仍读 session_store。
- **行为约束**：既有会话切换守卫语义不回退；现有前端测试 SHALL 无修改通过。

非目标（Out of scope）：

- 不迁移深度模式/管线时间线到 AG-UI（待 PoC 验收后另立 change）。
- 不做断点续跑（AG-UI run 易逝，刷新恢复仍靠现有持久化 + 快照重建）。
- 不解决 StreamRegistry 单 worker 架构约束（外置化另立 change）。

## Capabilities

### New Capabilities

- `chat-stream`: quick 模式对话流的 AG-UI 协议端点与 assistant-ui 渲染契约（事件序列、终止态、持久化一致、双轨隔离）。

### Modified Capabilities

- `frontend`: quick 模式消息流渲染层更换为 assistant-ui（交互行为语义不变：发送、流式增量、历史恢复、会话切换守卫）。

## Impact

- **后端**：`src/finance_agent/` 新增 AG-UI 端点模块（依赖 `ag-ui-protocol` Python SDK + LangGraph 适配）；`api.py` 注册路由；现有 `/api/stream` 不动。
- **前端**：新增 `@ag-ui/client` + assistant-ui 依赖；quick 模式渲染分支替换；streamStore 保留（管线/深度模式继续使用）。
- **测试**：后端 AG-UI 事件序列契约测试（事件类型顺序、终止态保证、持久化一致）；前端渲染组件测试；现有测试无修改通过。
- **风险**：双轨期两套流式通道并存，需在 spec 层明确边界防止回流蔓延。
