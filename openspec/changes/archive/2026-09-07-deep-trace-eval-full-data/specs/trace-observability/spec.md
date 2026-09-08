# Delta Spec: trace-observability

## MODIFIED Requirements

### Requirement: 深度分析根 span 携带评估数据

深度分析（deep_analysis）根 span 在建立时 SHALL 将调用方提供的用户查询写入 input（`{"stock_code": ..., "query": ...}`），并在退出前将完整报告正文与**评估数据段**写入 metadata，使 Langfuse hosted evaluator（LLM-as-judge）能以 `input.query`、`metadata.report_markdown` 及评估数据段绑定模板变量、并以 `metadata contains report_markdown` 过滤命中报告根 span。

- 调用方提供真实用户查询时 SHALL 原样写入；缺失时 SHALL 以 `深度分析 {stock_name}({stock_code})` 兜底，保证 input 恒含查询语义。
- `report_markdown` SHALL 为完整报告正文（非摘要截断），在根 span 退出前 update（对齐 content-fidelity「post-exit update 被丢弃」修复约定）。
- 根 span metadata SHALL 在退出前携带评估数据段：`analyst_reports`（**全量**分析师报告，含 `summary`/`key_findings`/`claims`/`markdown`，Pydantic 序列化，SHALL NOT 只放 200 字摘要）、`debate_history`（多空辩论消息全量列表）、`research_manager_decision`（源键 `research_manager_conclusion`）、`risk_judgment`（源键 `final_trade_decision`，Risk Judge 裁决）。
- `trade_decision`（`final_trade_decision`）与 `fund_manager_decision` 已存在于根 span output，SHALL NOT 重复写入 metadata。
- 评估数据段中任一源字段缺失（如无 debate_history）SHALL 省略对应 metadata 键、不抛异常（缺字段不造）。
- 快路径（api.py `_run_graph_streaming`）与 ReAct 工具路径（agent_factory `_stream_graph`）两个入口 SHALL 行为一致：input 含 query、metadata 含 report_markdown 与评估数据段。
- Langfuse 未配置时 SHALL 不抛异常、不影响业务流程（nullcontext 语义不变）。

#### Scenario: 快路径根 span 携带 query 与 report_markdown

- **WHEN** `_run_graph_streaming` 处理带 `req.query="深度分析600519"` 的分析请求且管线产出 final_report
- **THEN** 根 span input SHALL 含 `query="深度分析600519"`，退出时 SHALL 以 metadata `report_markdown` 写入完整报告

#### Scenario: ReAct 工具路径 query 兜底

- **WHEN** `_stream_graph` 经 run_deep_analysis 工具调用（无真实查询文本，仅 stock_code/stock_name）
- **THEN** 根 span input SHALL 含 `query="深度分析 贵州茅台(600519)"`（stock_name/stock_code 兜底）

#### Scenario: 根 span metadata 含全量评估段

- **WHEN** 管线退出且 accumulated 含 analyst_reports（4 个分析师对象含 markdown 全文）、debate_history（多轮消息）、research_manager_conclusion、final_trade_decision
- **THEN** 根 span metadata SHALL 含 `analyst_reports`（每分析师含 markdown 全文）、`debate_history`、`research_manager_decision`、`risk_judgment`，且 `report_markdown` 仍存在

#### Scenario: 缺字段不造

- **WHEN** accumulated 中某评估字段缺失（如无 debate_history）
- **THEN** 对应 metadata 键 SHALL 省略（不写入 None/空占位），不抛异常

#### Scenario: 无 Langfuse 零影响

- **WHEN** Langfuse 未配置（`get_langfuse()` 返回 None）
- **THEN** 管线 SHALL 正常执行，不抛异常，不创建观测