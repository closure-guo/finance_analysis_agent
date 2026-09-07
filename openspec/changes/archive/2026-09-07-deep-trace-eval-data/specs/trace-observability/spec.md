# Delta Spec: trace-observability

## ADDED Requirements

### Requirement: 深度分析根 span 携带评估数据

深度分析（deep_analysis）根 span 在建立时 SHALL 将调用方提供的用户查询写入 input（`{"stock_code": ..., "query": ...}`），并在退出前将完整报告正文写入 metadata 的 `report_markdown` 键，使 Langfuse hosted evaluator（LLM-as-judge）能以 `input.query` 与 `metadata.report_markdown` 绑定模板变量、并以 `metadata contains report_markdown` 过滤命中报告根 span。

- 调用方提供真实用户查询时 SHALL 原样写入；缺失时 SHALL 以 `深度分析 {stock_name}({stock_code})` 兜底，保证 input 恒含查询语义。
- `report_markdown` SHALL 为完整报告正文（非摘要截断），在根 span 退出前 update（对齐 content-fidelity「post-exit update 被丢弃」修复约定）。
- 快路径（api.py `_run_graph_streaming`）与 ReAct 工具路径（agent_factory `_stream_graph`）两个入口 SHALL 行为一致：input 含 query、metadata 含 report_markdown。
- Langfuse 未配置时 SHALL 不抛异常、不影响业务流程（nullcontext 语义不变）。

#### Scenario: 快路径根 span 携带 query 与 report_markdown

- **WHEN** `_run_graph_streaming` 处理带 `req.query="深度分析600519"` 的分析请求且管线产出 final_report
- **THEN** 根 span input SHALL 含 `query="深度分析600519"`，退出时 SHALL 以 metadata `report_markdown` 写入完整报告

#### Scenario: ReAct 工具路径 query 兜底

- **WHEN** `_stream_graph` 经 run_deep_analysis 工具调用（无真实查询文本，仅 stock_code/stock_name）
- **THEN** 根 span input SHALL 含 `query="深度分析 贵州茅台(600519)"`（stock_name/stock_code 兜底）

#### Scenario: 无 Langfuse 零影响

- **WHEN** Langfuse 未配置（`get_langfuse()` 返回 None）
- **THEN** 管线 SHALL 正常执行，不抛异常，不创建观测
