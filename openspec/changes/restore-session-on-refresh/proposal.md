# Proposal: restore-session-on-refresh

## Why

用户在深度分析（含 ReAct 股票搜索/澄清阶段）进行中刷新页面后，前端丢失全部内存态（`messages`、`currentSessionId`、`appState='empty'`），回到空状态首页，且**没有任何自动恢复当前会话的机制**——必须等用户手动点击侧边栏会话才能重新看到 agent 已输出的内容（工具调用、思考、管线进度）。用户感知为「输出消失了几秒」，体验割裂。

数据本身未丢失（后端 `chat_history` / `pipeline_snapshot` / 事件 journal 均完整），缺的是「刷新后自动回到进行中的会话」这一前端交互。

## What Changes

- 前端将 `currentSessionId` 持久化到 localStorage（新增 key，如 `fa_current_session_id`），在会话选中/创建/删除/新建分析时同步维护。
- 应用初始化（mount）时：加载会话列表后，若 localStorage 存在持久化的 `currentSessionId` 且该会话仍存在，则自动触发与「手动点击会话」等价的恢复逻辑（加载会话详情、重建消息、若 running 则重连事件流），无需用户手动点击。
- 持久化的会话已被删除或不存在时，清除该 localStorage 项并回退到空状态首页。
- 复用现有 `selectSession` 恢复路径（chat_history 重建 + running 时 SSE 重连），不引入新的恢复通道。

非目标（Out of scope）：
- 不改变后端 API、事件 journal、chat_history 持久化逻辑。
- 不改变手动切换会话的现有行为。
- 不处理「10s 增量 upsert 窗口导致重建内容落后实时最多 10s」的粒度问题（由既有 SSE 实时事件追上机制覆盖）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 扩展会话管理行为——新增「刷新后自动恢复当前会话」需求。现状 spec 的 `Session Selection`/`Session List Loading` 仅覆盖「初始化加载列表」与「手动点击会话恢复」，未定义刷新后自动恢复进行中的会话。本变更新增该行为契约（持久化 currentSessionId + mount 自动恢复），属需求级新增。

## Impact

- **前端**：`frontend/src/App.tsx`（currentSessionId 持久化、mount 自动恢复逻辑）、可能涉及 `frontend/src/types.ts`。
- **localStorage**：新增 key `fa_current_session_id`（与既有 `fa_user_id`/`fa_api_key` 同风格）。
- **后端**：无改动。
- **测试**：新增前端单元/组件测试（刷新后自动恢复进行中会话、会话已删除回退空态）；交互行为变更需人工验证报告落 `tests/validation/`。
- **E2E**：属交互行为变更，按项目红线需 E2E 门禁（真实前后端，模拟刷新恢复链路）。
