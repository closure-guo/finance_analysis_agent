## Why

当前 [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) 的规则预处理逻辑伪装成 LLM 的事件，导致「规则归规则、LLM 归 LLM」的边界被打破：

- **① 时效性预搜索**（[api.py:1208-1260](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L1208-L1260)）：规则匹配时效关键词后，冒充 `thinking_token`（"用户询问包含时效性关键词，我先搜索..."）+ `tool_call` + `tool_result` + `search_start/result`，用户以为是 LLM 在思考并决策调用工具，实际是规则触发的预搜索。
- **②③ 管线节点进度/摘要**（[api.py:780-784](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L780-L784) / [822-826](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L822-L826)）：node_start 后冒充 `thinking_token`（"▶ 正在执行..."），node_complete 后冒充 `thinking_token`（"✓ 摘要..."），用户以为是 LLM 在思考，实际是系统进度提示。

后果：Langfuse trace 看不到规则决策（黑盒）；调试时 grep 不到规则逻辑（散在 api.py）；前端无法区分真假事件。本 delta 建立规则透明层，把规则预处理从「地下工作者」变成「正式员工」——给它独立的事件类型、独立的 trace span、独立的代码模块，不再冒充 LLM。

## What Changes

- 新增 `transparent-system-events` capability，定义规则层与系统层的事件契约：
  - `rule_triggered` / `rule_pre_search_start` / `rule_pre_search_complete` 事件（① 时效性预搜索，chat 流）
  - `system_note` 事件（②③ 管线节点进度/摘要，analyze 流，用 `kind=node_progress|node_summary` 区分）
  - 规则层 Langfuse span 规范（`rule_preprocessing` / `pre_search` span）
- **MODIFIED `frontend` capability**（仅 ADDED 新 requirement，不改现有 requirement，与 `enable-deepseek-thinking-mode` delta 零冲突）：
  - ADDED `Rule-Triggered Event Handling`：chat 流对 `rule_triggered` / `rule_pre_search_*` 的处理
  - ADDED `System Note Event Handling`：analyze 流对 `system_note` 的处理（渲染为系统提示，区别于 ThinkingBanner）
- 新建 `src/finance_agent/rules/` 模块（`base.py` + `temporal_search_rule.py` + `system_notes.py`），承接从 api.py 迁出的三处冒充逻辑。
- [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) 退化为薄编排层：调用 rules/ 模块获取事件、转发 LLM 流，不再生成任何伪 `thinking_token` / 伪 `tool_call`。
- 前端 [types.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/types.ts) 新增事件类型，[App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) 新增 `system_note` / `rule_triggered` 处理分支。

## Capabilities

### New Capabilities

- `transparent-system-events`: 规则层与系统层事件契约，定义 `rule_triggered` / `rule_pre_search_*` / `system_note` 事件类型、字段、触发时机，以及规则层 Langfuse span（`rule_preprocessing` / `pre_search`）的命名与字段规范。

### Modified Capabilities

- `frontend`: ADDED 两个新 requirement（`Rule-Triggered Event Handling`、`System Note Event Handling`），描述前端对新事件类型的处理。**不 MODIFIED 任何现有 requirement**——①②③ 的冒充行为是代码实现，现有 spec 未描述冒充场景，因此移除冒充不需改 spec；新事件用独立 requirement 承载，与 `enable-deepseek-thinking-mode` delta 改动的 `Conversation Stream Common Events` / `Pipeline Thinking Display` 不重叠，零冲突。

## Impact

- **代码**：新建 `src/finance_agent/rules/`（3 文件）、[api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) 迁出三处冒充逻辑、[frontend/src/types.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/types.ts) + [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) 新增事件处理。
- **事件流**：新增 4 个事件类型（`rule_triggered` / `rule_pre_search_start` / `rule_pre_search_complete` / `system_note`）；移除 3 处冒充（伪 `thinking_token` / 伪 `tool_call` / 伪 `tool_result`）。现有 `thinking_token` / `tool_call` / `search_*` 语义不变（只承载真实 LLM/工具/搜索事件）。
- **可观测性**：Langfuse trace 新增 `rule_preprocessing` / `pre_search` span（规则层可观测）；与 `trace-observability` delta 的 `tool` / `search_api_call` span 共同构成完整分层。
- **依赖**：规则层 span 复用 `trace-observability` delta 引入的 `open_span` helper；建议 `trace-observability` 先 archive，本 delta 直接使用 helper。若本 delta 先实施，需先实现 `open_span`（或临时内联）。
- **协调**：与 `enable-deepseek-thinking-mode` delta 都涉及 `frontend` capability，但本 delta 只 ADDED 新 requirement，不改其 MODIFIED 的 `Conversation Stream Common Events`，两个 delta 可独立 archive、任意顺序 sync。
- **风险**：中。涉及前端 UI + 事件流契约变更 + 与 ②delta 协调，比 `trace-observability` delta 复杂。
