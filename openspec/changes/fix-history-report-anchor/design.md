# Design: fix-history-report-anchor

## Context

历史会话重建时，前端 `selectSession`（App.tsx）把管线完成时间轴 + 报告消息固定在**第一个** user 消息后插入。`chat_history` 是纯时间序数组（`append_chat` 追加），报告单独存 `report_markdown`，历史中没有记录管线在对话流中的触发位置。

两种历史形态需要不同的插入位置，纯前端无法区分：

| 场景 | chat_history 形态 | 正确插入点 |
|------|------------------|-----------|
| 澄清后分析 | `[user1, assistant1, user2]` | 最后一条 user 后 |
| 报告后追问 | `[user1, user2, assistant2]`（fast path 不落 assistant） | 第一条 user 后 |

约束：SQLite 单文件库，schema 迁移走 `session_store.init_db` 的幂等 ALTER TABLE 模式；旧会话无锚点数据需回退兼容。

## Goals / Non-Goals

**Goals:**
- 多轮澄清场景下历史重建的消息顺序与实时渲染顺序一致：用户消息 → agent 思考/工具 → 用户确认 → 管线卡 → 报告卡
- 报告后追问场景保持现有正确顺序，不回归
- 旧会话（无锚点）行为不变

**Non-Goals:**
- 不改变实时渲染路径的任何逻辑
- 不处理同一 session 多次触发管线的历史保留（现状 report_markdown 也只保留最近一次，锚点语义一致）
- 不重构 chat_history 数据模型（不引入 marker 条目）

## Decisions

### D1: 锚点语义 = 「最后一条 user 消息索引 + 1」，管线启动时持久化

新增 sessions 表列 `pipeline_anchor INTEGER`（NULL = 无锚点）。管线启动时由后端写入：`chat_history` 中最后一条 `role='user'` 的索引 + 1，即"触发本轮分析的用户消息之后"。

**选此而非「chat_history 长度」**：ReAct 路径下当前轮 assistant 在途消息可能已被 10s 增量 upsert（`_upsert_assistant_chat`）进 chat_history，取长度会把该在途消息算入锚点之前，导致重建时 agent 思考块与管线卡的相对顺序随 upsert 时机（10s 边界）抖动。锚定 user 消息则结果稳定：assistant 在途/最终消息恒在锚点之后，渲染为「管线卡 → 报告卡 → assistant 总结」，语义自然（先报告后总结）。

**选此而非 chat_history marker 条目**：marker 会污染 `_inject_chat_history`（agent 上下文注入）与 follow-up prompt 的历史文本，所有消费方都需加过滤；独立列零侵入。

### D2: 写入点 = 两处管线启动路径，统一收口 session_store

新增 `session_store.set_pipeline_anchor(session_id)`：读 chat_history 定位最后一条 user，UPDATE 列。调用点：
- fast path：`api.py` `stock_code and not req.session_id` 分支，`append_chat(user)` 之后、`PipelineRunner.start` 之前
- ReAct 路径：`agent_factory._make_run_deep_analysis` 的 `run_deep_analysis` 工具体内，管线实际启动时（此处能拿到 session_id 闭包）

**不取 chat_history 长度作参数传入**：由 session_store 内部读表计算，调用点无感，避免两处各自实现。

### D3: 前端按锚点插入，无锚点回退旧逻辑

`SessionDetail` 增加 `pipeline_anchor?: number | null`。`selectSession` 重建：
- 锚点非空：遍历 chat_history 构建消息，处理完第 `anchor` 条后立即插入 pipelineDoneMsg + reportMsg（替代现 `reportInserted` 的"第一个 user"条件）
- 锚点为 NULL（旧会话）：保持「第一个 user 消息后」回退，行为零变化

running 会话的 runningPipelineMsg 现追加在末尾；统一改走锚点后在 fast path 下等价（锚点 = 末尾），ReAct running 重建属刷新页面的少数路径，顺序同样更贴近真实时序。

### D4: spec 修正

frontend spec「恢复会话对话历史」Scenario 中「在第一个用户消息后插入报告消息」改为「在管线触发锚点（pipeline_anchor）之后插入；无锚点旧会话回退第一个用户消息后」。session-persistence spec 新增锚点持久化 requirement。

## Risks / Trade-offs

- [同一 session 二次触发管线，锚点被覆盖，旧报告位置丢失] → 与 report_markdown 只留最近一次的现状语义一致，可接受；多次分析的历史保留属独立议题
- [旧会话无锚点仍错位] → 无法回溯推断（chat_history 无管线时间信息），回退保持现状，只保证新会话正确
- [ReAct 路径 assistant 总结消息渲染在报告之后，与实时流中「思考块在管线卡前」略有差异] → 用户消息与管线/报告的核心时序正确；assistant 尾总结放报告后语义自然

## Migration Plan

1. `session_store.init_db` 迁移列表加 `("pipeline_anchor", "ALTER TABLE sessions ADD COLUMN pipeline_anchor INTEGER")`，幂等，启动自动执行
2. 后端先发（新列对旧前端无感，详情响应多一个字段）
3. 前端后发（读到 NULL 走回退）
4. 回滚：前端回滚即恢复旧行为；列保留无害
