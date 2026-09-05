# Proposal: fix-analysis-ux-polish

## Why

股票分析（含 ReAct 澄清/深度分析）过程中存在四个独立的 UI/交互缺陷，均为真实用户实测发现：

1. **「已用时」刷新后归零**：管线进度横幅的「已用时」用前端本地时间戳 `msg.startedAt = Date.now()` 计算，刷新后 `startedAt` 丢失/重置为重建时刻，已用时归零。它读的不是后端管线真实启动时间。
2. **工具执行中仍可发送消息**：澄清阶段 agent 调用工具（如「识别股票」执行中）时，用户仍能在输入框连续发送多条消息。根因是追问路径后端不重发 `session_created`，前端 `localAbort` 从未登记进 `streamRegistry`，`isSessionRunning` 两个判定条件（`session.status==='running'` 滞后、streamRegistry 无未中断 abort）同时失效返回 false，拦截旁路。
3. **「会话正在生成中」警告层级不对**：该警告锚定在 `bottom:90px`、与停止按钮耦合、z-index 40 与输入框同级，位置在视口底部而非顶部，被输入框渐变背景糊住，用户期望「浮在最上面可见」。
4. **意图澄清回复格式错乱**：实时流式渲染时回复正文单 `\n` 丢失、列表项粘连、句子串行；刷新后（走落库文本重建）恢复正常。根因待进一步定位（端到端 chat_token 路径测试正常，疑与 thinking 流/DSML 剥离路径的换行处理有关）。

## What Changes

- **已用时后端计时**：后端管线快照新增 `pipeline_start_ts`（管线启动时间戳，毫秒），在 `_persist_snapshot` 中随快照持久化；前端 `selectSession` 重建 running 管线时用快照的 `pipeline_start_ts` 作为 `msg.startedAt`，而非 `Date.now()`。
- **工具执行中禁止输入**：前端 `startAnalysis` / `quickChat` 在 fetch 发出前、已知 sessionId 时，与 `streamingSessionIdRef` 补丁同位置补 `getStreamState(sessionId).abort = localAbort`，使 `isSessionRunning` 覆盖「同一会话工具执行中」状态。
- **warning 顶部 toast**：把 warningMessage 从「停止按钮容器」拆出，改为独立的 fixed 顶部 toast（`fixed top-16 z-[60] left-1/2 -translate-x-1/2`），自动消失逻辑（setTimeout 3s）不变；停止按钮容器保持原样。
- **澄清回复格式**：定位并修复实时流式渲染丢 `\n` 的环节（先补复现测试，再修）。

非目标（Out of scope）：
- 不改变后端管线状态机、事件 journal、chat_history 语义。
- 不改变「会话生成中」的拦截触发时机与文案，仅改展示层级。
- 不重构 isSessionRunning / streamRegistry 整体机制，仅补追问路径的 abort 登记。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 修改四处交互契约——
  - 管线 ETA/已用时计时源由前端本地改为后端管线启动时间戳（刷新不归零）。
  - 会话内发送在「工具执行中/会话运行中」一律拦截（含追问路径）。
  - 「会话生成中」警告以 fixed 顶部 toast 呈现。
  - 澄清回复实时流式渲染与落库文本格式一致（不丢 `\n`）。
- `backend`: 管线快照契约新增 `pipeline_start_ts` 字段（向后兼容：缺省时前端回退本地时间）。

## Impact

- **后端**：`src/finance_agent/agent_factory.py`（`_persist_snapshot` 增 `pipeline_start_ts`，取 `_pipeline_start_time`）。
- **前端**：`frontend/src/App.tsx`（selectSession 重建 startedAt、startAnalysis/quickChat abort 登记、warning toast 渲染）、`frontend/src/types.ts`（快照类型增 `pipeline_start_ts`）。
- **测试**：后端快照含启动时间戳测试；前端组件测试（重建 startedAt 用快照值、工具执行中拦截、warning 顶部 toast）；格式修复复现测试。
- **验证**：交互行为变更，人工验证报告落 `tests/validation/`；按红线需 E2E 门禁。
