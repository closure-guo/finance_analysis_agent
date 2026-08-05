# Proposal: fix-history-report-anchor

## Why

历史会话重建时气泡错位：多轮澄清场景（用户「分析一下热门股票」→ agent 搜索思考 → 用户「中际旭创」→ 管线执行）下，报告卡与管线进度卡被渲染在第一个用户消息之后，导致 assistant 的思考/工具调用块与第二条用户消息被挤到报告之后，时序完全颠倒。

根因：前端 `selectSession` 将报告消息固定插入在**第一个** user 消息后，而当前 spec 也如此定义。该定义只覆盖 fast path 单轮场景（chat_history 仅一条 user），多轮澄清场景行为未定义。且纯前端启发式（第一条/最后一条 user）无法同时兼容「澄清后分析」与「报告后追问」两种历史形态——chat_history 中缺少管线触发锚点。

## What Changes

- 后端在管线启动时（fast path `PipelineRunner.start` 与 ReAct `run_deep_analysis` 工具两处）持久化锚点：`pipeline_anchor` = 启动时刻 chat_history 的条目数，存入 sessions 表新列。
- 会话详情接口（GET /api/sessions/{id}）返回 `pipeline_anchor` 字段。
- 前端历史重建改为按锚点插入：管线完成时间轴 + 报告消息插入到 chat_history 第 N 条（锚点）之后；无锚点的旧会话回退到现有「第一个用户消息后」行为（兼容）。
- **BREAKING（spec 语义修正）**：删除/修正 frontend spec「非 chat 类型的会话在第一个用户消息后插入报告消息」的表述，改为按管线触发锚点插入。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 「恢复会话对话历史」Scenario 中报告消息插入位置从「第一个用户消息后」改为「管线触发锚点之后」，并定义无锚点旧会话的回退行为。
- `session-persistence`: 新增管线触发锚点的持久化契约（`pipeline_anchor` 列的写入时机与会话详情返回）。

## Impact

- 后端：`src/finance_agent/session_store.py`（schema 迁移加列 + 读写）、`src/finance_agent/api.py`（fast path 与 ReAct 路径管线启动时写锚点）。
- 前端：`frontend/src/App.tsx`（selectSession 重建逻辑）、`frontend/src/types.ts`（SessionDetail 增加字段）。
- 数据迁移：SQLite ALTER TABLE 加列，旧会话为 NULL 走回退逻辑，无数据改写。
- 测试：`frontend/src/test/selectSession.test.tsx`（多轮澄清场景复现测试）、后端 session_store/api 测试。
