## ADDED Requirements

### Requirement: Rule-Triggered Event（时效性预搜索）

系统 SHALL 在 chat 流中，当用户查询命中时效性规则（含时效关键词且无股票代码）时，依次发布 `rule_triggered`、`rule_pre_search_start`、`rule_pre_search_complete` 三个事件，SHALL NOT 发布伪 `thinking_token` / 伪 `tool_call` / 伪 `tool_result` 来冒充 LLM 决策。

#### Scenario: 命中规则时发布 rule_triggered

- **WHEN** chat 流收到用户查询，且查询含时效性关键词且无股票代码
- **THEN** 系统 SHALL 发布 `rule_triggered` 事件，含 `rule`（规则标识，如 "time_sensitive_presearch"）与 `reason`（触发原因）字段

#### Scenario: 预搜索开始时发布 rule_pre_search_start

- **WHEN** rule_triggered 发布后、预搜索执行前
- **THEN** 系统 SHALL 发布 `rule_pre_search_start` 事件，含 `query` 字段

#### Scenario: 预搜索完成时发布 rule_pre_search_complete

- **WHEN** 预搜索执行完成
- **THEN** 系统 SHALL 发布 `rule_pre_search_complete` 事件，含 `query`、`results`（搜索结果数组）、`count`（结果数量）字段

#### Scenario: 不命中规则时不发布任何规则事件

- **WHEN** chat 流收到用户查询，但查询不含时效关键词或含股票代码
- **THEN** 系统 SHALL NOT 发布任何 `rule_triggered` / `rule_pre_search_*` 事件

#### Scenario: 不再发布伪 thinking_token 与伪 tool_call

- **WHEN** 规则触发预搜索
- **THEN** 系统 SHALL NOT 发布 `thinking_token` 事件来冒充 LLM 思考
- **AND** SHALL NOT 发布 `tool_call` / `tool_result` 事件来冒充 LLM 工具调用
- **AND** 搜索的执行与结果由 `rule_pre_search_*` 事件承载，不混入 `search_start` / `search_result`（那些保留给真实 LLM 工具调用搜索）

### Requirement: System Note Event（管线节点进度与摘要）

系统 SHALL 在 analyze 流的管线节点生命周期中发布 `system_note` 事件：node_start 后发布 `kind=node_progress`，node_complete 后发布 `kind=node_summary`，SHALL NOT 发布伪 `thinking_token` 来冒充 LLM 思考。

#### Scenario: node_start 后发布 node_progress

- **WHEN** analyze 流的 graph.stream 循环收到 node_start 事件
- **THEN** 系统 SHALL 发布 `system_note` 事件，`kind` 为 `node_progress`，含 `node`（节点名）与 `text`（进度提示，如 "▶ 正在执行：技术分析…"）字段

#### Scenario: node_complete 后发布 node_summary

- **WHEN** analyze 流的 graph.stream 循环收到 node_complete 事件
- **THEN** 系统 SHALL 发布 `system_note` 事件，`kind` 为 `node_summary`，含 `node`（节点名）与 `text`（节点摘要）字段

#### Scenario: 不再发布伪 thinking_token

- **WHEN** 管线节点执行
- **THEN** 系统 SHALL NOT 发布 `thinking_token` 事件来冒充 LLM 思考进度或摘要
- **AND** 管线的真实 LLM 思考仍由 `thinking_token` 承载（来源 reasoning_content），系统提示由 `system_note` 承载，两者分离

### Requirement: Rule Layer Langfuse Span

系统 SHALL 为规则预处理在 Langfuse trace 中创建独立的 `rule_preprocessing` span 与 `pre_search` span，使规则决策可观测、可审计。

#### Scenario: 规则触发时创建 rule_preprocessing span

- **WHEN** 规则命中并触发预搜索
- **THEN** 系统 SHALL 创建 `rule_preprocessing` span（as_type=span），input 字段含 `rule`（规则标识）与 `reason`（触发原因）

#### Scenario: 预搜索时创建 pre_search span

- **WHEN** 规则触发的预搜索执行
- **THEN** 系统 SHALL 创建 `pre_search` span（as_type=span）作为 `rule_preprocessing` span 的子 span，input 含 `query`，output 含 `count` 与 `results`

#### Scenario: 规则未触发时不创建 span

- **WHEN** 规则未命中（不触发预搜索）
- **THEN** 系统 SHALL NOT 创建 `rule_preprocessing` 或 `pre_search` span

### Requirement: Rule Layer Code Isolation

规则层逻辑 SHALL 集中在 `src/finance_agent/rules/` 模块，[api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) SHALL NOT 直接生成规则事件或系统提示事件，只调用 rules/ 模块获取事件并转发。

#### Scenario: 规则代码集中在 rules 模块

- **WHEN** 需要判断时效性规则或生成系统提示
- **THEN** 系统 SHALL 通过 `rules/temporal_search_rule.py`（①）或 `rules/system_notes.py`（②③）提供的能力完成，api.py 不含规则判断或事件生成逻辑

#### Scenario: api.py 仅转发规则层产出

- **WHEN** api.py 处理 chat 流或 analyze 流
- **THEN** api.py SHALL 调用 rules/ 模块获取 RuleEvent / SystemNoteEvent，并转发为 SSE 事件
- **AND** api.py SHALL NOT 直接构造 `rule_triggered` / `system_note` / 伪 `thinking_token` 事件
