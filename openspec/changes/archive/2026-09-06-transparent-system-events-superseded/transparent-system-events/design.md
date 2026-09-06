## Context

当前 [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) 把规则预处理逻辑伪装成 LLM 事件，三处冒充：

- **① 时效性预搜索**（[api.py:1208-1260](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L1208-L1260)，chat 流）：规则匹配时效关键词后，冒充 `thinking_token` + `tool_call` + `tool_result` + `search_start/result`。
- **② node 进度**（[api.py:780-784](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L780-L784)，analyze 流）：node_start 后冒充 `thinking_token`（"▶ 正在执行..."）。
- **③ node 摘要**（[api.py:822-826](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L822-L826)，analyze 流）：node_complete 后冒充 `thinking_token`（"✓ 摘要..."）。

现有事件类型已按来源分 5 类（LLM 回复 / Web Search / Tool Call / 管线进度 / 会话状态），分类本身正确，问题在规则层「借用」了 LLM 回复类（thinking_token）和工具调用类（tool_call/tool_result）来伪装自己。现有 Langfuse 适配已覆盖 LLM generation span、管线节点 span、ReAct loop span，但规则层零埋点。

## Goals / Non-Goals

**Goals:**

- ① 时效性预搜索改发 `rule_triggered` / `rule_pre_search_start` / `rule_pre_search_complete`，不再冒充 thinking_token/tool_call。
- ②③ 管线节点进度/摘要改发 `system_note`（kind 区分），不再冒充 thinking_token。
- 规则层有独立 Langfuse span（`rule_preprocessing` / `pre_search`）。
- 规则代码集中到 `src/finance_agent/rules/` 模块，api.py 退化为薄编排层。
- 前端识别新事件类型，渲染差异化 UI（系统预处理/系统提示，区别于 ThinkingBanner）。

**Non-Goals:**

- 不改 LLM 回复类事件（thinking_token/chat_token）的语义——它们只承载真实 LLM 输出（与 `enable-deepseek-thinking-mode` delta 的净化方向一致）。
- 不改 Web Search / Tool Call 事件类型——它们已经正确分类（搜索有独立 `search_*`，工具调用有独立 `tool_call`）。
- 不补工具调用 span / 网络搜索 span——属于 `trace-observability` delta 的范围。
- 不补管线节点内数据获取 span（fetch.py/compute.py）——留给后续独立 delta。
- 不改 LangGraph 5 层管线内部逻辑——规则透明层只改事件发布与 trace span，不改管线节点行为。

## Decisions

### 决策 1：新建 `src/finance_agent/rules/` 模块，三文件分工

**选择**：`rules/` 下分 `base.py`（RuleEvent 数据结构 + span 辅助）、`temporal_search_rule.py`（① chat 流）、`system_notes.py`（②③ analyze 流）。

**理由**：① 在 chat 流、②③ 在 analyze 流，触发时机与场景不同，分文件符合单一职责；`base.py` 提供共享的 RuleEvent 与 span 辅助，避免重复。

**备选**：单文件 `rules.py`。否决——chat 流与 analyze 流逻辑差异大，单文件会重新变成混杂层。

### 决策 2：`system_note` 用 `kind` 字段区分 ②③，不拆两个事件类型

**选择**：一个 `system_note` 事件 + `kind: node_progress | node_summary` 字段。

**理由**：②③ 产生模块相同（`system_notes.py`）、消费场景相同（analyze 管线 UI）、本质同类（系统生成的展示提示），只是触发时机（node_start vs node_complete）与内容（进度 vs 摘要）不同。用 kind 区分即可，拆两个类型是过度设计。

### 决策 3：对 `frontend` capability 只 ADDED 新 requirement，不 MODIFIED 现有 requirement

**选择**：在 `frontend` delta spec 里用 `## ADDED Requirements` 新增 `Rule-Triggered Event Handling` 与 `System Note Event Handling`，不碰现有 requirement。

**理由**：①②③ 的冒充行为是代码实现，现有 spec 未描述冒充场景（`Conversation Stream Common Events` 只说「收到 thinking_token 怎么处理」，不管来源），因此移除冒充不需改 spec。新事件用独立 requirement 承载，与 `enable-deepseek-thinking-mode` delta MODIFIED 的 `Conversation Stream Common Events` 不重叠，两个 delta 可独立 archive、任意顺序 sync，零冲突。

**备选**：MODIFIED `Conversation Stream Common Events` 加新 scenario。否决——会与 enable-deepseek delta 改同一 requirement，sync 时 textual 冲突。

### 决策 4：规则层 span 复用 `trace-observability` delta 的 `open_span` helper

**选择**：`rules/base.py` 从 `langfuse_tracing` import `open_span`，规则层 span 用 `open_span(name="rule_preprocessing", input=...)` 创建。

**理由**：复用公共 helper 避免重复；`open_span` 已封装优雅降级（未配置 Langfuse 返回 nullcontext），规则层无需重新实现。

**依赖**：建议 `trace-observability` delta 先 archive，本 delta 直接使用 helper。若本 delta 先实施，需先实现 `open_span`（或临时内联，archive 前对齐）。

### 决策 5：api.py 退化为薄编排层

**选择**：api.py 不再直接生成任何伪 thinking_token / 伪 tool_call，只调用 rules/ 模块获取 RuleEvent 并转发为 SSE。

**理由**：让规则归规则、LLM 归 LLM。api.py 只负责请求接入 → 调用规则层 → 转发 LLM 流 → 转发管线事件，规则判断与事件生成全部下沉到 rules/ 模块。

## Risks / Trade-offs

- **[与 `enable-deepseek-thinking-mode` delta 的 frontend 协调]** → 本 delta 只 ADDED 新 requirement，不改其 MODIFIED 的 requirement，零 textual 冲突；两个 delta 可任意顺序 sync。需在实施时确认 ②delta 的 `thinking_token` 净化（来源 reasoning_content）与本 delta 的「不再发伪 thinking_token」方向一致——两者互补，不矛盾。
- **[与 `trace-observability` delta 的 helper 依赖]** → 规则层 span 依赖 `open_span` helper。建议 `trace-observability` 先 archive；若并行实施，本 delta 的 `rules/base.py` 先内联 span 逻辑，待 helper 可用时切换为 import。
- **[前端 UI 差异化渲染的新增工作量]** → 新增 `system_note` / `rule_triggered` 的 UI 处理分支，需在 App.tsx 增加渲染逻辑。系统提示 UI 可复用现有 Timeline 机制（新 item 类型），不引入新组件库。
- **[事件流契约变更的回归风险]** → 移除 ①②③ 冒充事件后，依赖 thinking_token 累积的逻辑（如 `extractThinkingTitle`）不再收到冒充 token，需回归测试管线 UI 与 chat 流的思考展示不受影响。
- **[rules/ 模块对 api.py 内部函数的依赖]** → ① 的预搜索复用 `agent_factory._web_search`，规则层不应依赖 agent_factory 内部函数。改造时将 `_web_search` 提取为 `web_search.py` 的公共函数，规则层 import 公共函数，避免模块耦合。
