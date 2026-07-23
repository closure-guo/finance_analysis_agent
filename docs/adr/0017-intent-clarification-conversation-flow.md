# ADR-0017: Intent Clarification as Conversation Flow in Deep Mode

**Status**: Accepted  
**Date**: 2026-07-15

## Context

当前深度模式的前置意图澄清环节由独立的 `/api/clarify` 端点和前端 `ClarifyCard` 组件实现：

- 后端先调用 `search_stock` 解析股票，再调用独立 LLM 生成 `understanding` + `questions`，最后以 `clarify_done` SSE 事件推送到前端。
- 前端渲染一个特殊卡片：展示意图理解、候选股票列表、1-2 个澄清问题，并卡片内嵌 textarea 让用户填写 `focus`。
- 用户点击"开始深度分析"按钮后，才把 `stock_code` + `focus` 传入 `/api/analyze` 启动 5 层管线。

这个实现与 Kimi-Researcher 的交互模式不一致。Kimi 在深度研究任务中不会弹出独立选择卡片，而是：

1. 接收用户输入后，先以普通助手消息确认研究目的、澄清模糊点；
2. 用户在主输入框回复；
3. 澄清完成后再自然过渡到搜索/分析执行；
4. 整个澄清-分析-追问链路都在同一会话对话流内。

此外，独立端点导致两套股票解析和意图理解逻辑并存（`/api/clarify` vs ReAct Agent 的 `search_stock` 工具），与 ADR-0014 的"统一 ReAct Agent 编排层"原则冲突。

## Decision

### D1: 深度模式入口统一走 ReAct Agent 对话流

废弃独立的 `/api/clarify` 端点和 `ClarifyCard` 组件。用户进入"深度模式"后，所有交互都通过 `/api/analyze` 上的 ReAct Agent 处理。Agent 通过 `search_stock` 解析标的，通过 prompt 驱动的自主判断决定是反问还是直接执行 `run_deep_analysis`。

澄清回复以普通对话消息（`chat` 类型 SSE 事件）流式输出，用户在主输入框回答。

### D2: 反问触发条件由 Agent 自主判断

`deep_mode.md` system prompt 中明确以下 Workflow：

1. 先调用 `search_stock` 解析用户输入中的股票；
2. 如果 `search_stock` 返回多个候选或置信度低，向用户提出澄清问题，确认具体标的；
3. 如果用户只给了股票但没有明确分析意图，提出 1-2 个澄清问题（关注基本面/技术面/估值/舆情？短期/长期？是否同业对比？）；
4. 如果用户输入包含"推荐"、"热点"、"为什么涨"等时效性/不确定性词，先调用 `web_search` 获取信息，再决定是否反问；
5. 当信息足够明确时，调用 `run_deep_analysis`。

Agent 单次对话中最多进行 1 轮澄清；若用户仍不明确，则基于当前最佳理解继续执行。

### D3: Session 生命周期从首次用户输入开始

复用 SQLite `sessions` 表（ADR-0012），扩展字段以支持 clarify 阶段：

- `stock_code`、`stock_name`：改为可空，clarify 阶段可能尚未确定最终标的；
- `focus`：记录澄清阶段收集的用户关注点；
- `pending_intent`：记录当前等待状态，如 `awaiting_stock`、`awaiting_focus`、`''`；
- `status` 新增 `clarifying` 状态，与 `running` / `completed` / `failed` 并列。

Session 在 ReAct Agent 收到首次深度模式输入时立即创建，而非等 pipeline 完成后回填。`chat_history` 从 session 创建开始累积，包括 clarify 对话和后续追问。

### D4: `focus` 从用户回答中自然聚合

Agent 收到用户对澄清问题的回复后，将回复内容追加到 session 的 `focus` 字段。当 Agent 最终调用 `run_deep_analysis` 时，将 `focus` 作为参数传入，注入 5 层管线的初始状态。具体提取策略由 prompt 引导：

```markdown
When the user replies to a clarification question, append the answer to the `focus` field. When calling run_deep_analysis, include the collected focus.
```

不需要单独的结构化提取函数，由 LLM 在 ReAct 上下文中自行决定 `focus` 的累积方式。

### D5: Langfuse Session 保持 1:1 映射

项目 Session 与 Langfuse Session 同名但不同义（参见 CONTEXT.md）。`session_id` 在 Agent 首次创建 session 时生成，同时作为 `langfuse_session_id` 上报到 Langfuse，用于聚合一次完整分析任务的所有 Trace。澄清阶段产生的 Trace 也归入同一个 Langfuse Session。

## Consequences

### 正面

- 与 Kimi 深度研究交互模式一致，降低用户认知成本；
- 消除 `/api/clarify` 与 ReAct Agent 的股票解析重复逻辑；
- 澄清阶段自然进入 session 历史，后续追问可获得更完整上下文；
- 前端交互简化：移除 `ClarifyCard` 特殊状态，统一使用对话消息流；
- 状态持久化后，浏览器刷新或重连可恢复 clarify 等待状态。

### 负面

- `sessions` 表 schema 需要迁移（`stock_code`/`stock_name` 可空，新增 `focus`/`pending_intent`）；
- `/api/analyze` 需要处理 `stock_code` 为空的情况：第一次请求可能只携带 `query`；
- 前端 `appState` 需要新增 `clarifying` 状态；
- 删除旧端点和组件后，需要更新类型定义和可能的测试用例；
- 依赖 LLM 自主判断何时反问，可能需要通过 prompt 迭代和观测调优稳定性。

### 风险

- LLM 可能在不必要时反复反问，或该反问时不反问。缓解：通过 prompt 中的明确规则和最大 1 轮限制约束；
- Session 表从"报告完成后创建"改为"首次输入即创建"，可能产生大量用户只发了问题但未继续的"孤儿 session"。缓解：侧边栏默认不显示 `clarifying` 状态 session，或定时清理；
- 多候选场景下 Agent 可能选错默认标的。缓解：prompt 要求 Agent 在 understanding 中明确说明默认选择，并允许用户通过回答切换。

## Alternatives Considered

| 方案 | 否决理由 |
|------|---------|
| 保留独立 `/api/clarify` 端点，只改前端 UI | 后端仍有重复逻辑，与 ADR-0014 统一编排层冲突；Kimi 模式本质是 Agent 自主决策，不是端点包装 |
| 保留 ClarifyCard 但去掉候选选择，保留 textarea | 仍使用卡片内输入，不符合 Kimi 主输入框对话流 |
| 使用独立 Agent 状态机表，不扩展 sessions 表 | 用户视角的一次完整分析任务被拆到两张表，查询和生命周期管理更复杂 |
| 不持久化 clarify 状态，全靠长上下文恢复 | 刷新页面后状态丢失，与 ADR-0012 的中断恢复设计冲突 |

## Related

- ADR-0012: Session Management, Streaming, and Natural Language Input
- ADR-0014: Adopt Agent Harness as Unified Orchestration Layer
- CONTEXT.md: "Session", "Deep Mode", "Natural Language Input"
