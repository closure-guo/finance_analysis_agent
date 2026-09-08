# Proposal: deep-trace-eval-data

## Why

Langfuse hosted evaluator（LLM-as-judge，enable-hosted-evaluator）要给「整份报告 vs 用户查询」打分，需要 deep_analysis 根 span 上能取到两个东西：**用户查询**与**完整报告正文**。现状（实测 ClickHouse）：

- 根 span `input` 只有 `{"stock_code": "600519"}`，**无用户查询**；
- 根 span `output` 只有报告前 500 字摘要（`_build_trace_output` 截断），**无完整报告**；
- api.py 快路径根 span `output` 甚至为 NULL（退出时从不 update）。

结果：hosted evaluator 无论绑 trace 还是根 span，`{{query}}`/`{{report}}` 都取不到有效内容——报告评审 evaluator 无法工作（已与用户确认此缺口是 report_relevance 等四个评审 evaluator 的前置阻塞）。

## What Changes

- **根 span `input` 增加 `query`**：`{"stock_code": ..., "query": <用户查询>}`。用户查询从调用方可得（api.py 快路径 `req.query`）；ReAct 工具路径无真实查询文本（工具只收 stock 参数），退回 `"深度分析 {stock_name}({stock_code})"` 表示「分析对象」，保证 input 恒有查询语义。
- **根 span `metadata` 增加 `report_markdown`**：退出时写入完整报告正文，供 hosted evaluator 以 `metadata.report_markdown`（变量映射 `jsonSelector`）取用，同时作为 `metadata contains report_markdown` filter 的选择依据（observation evaluator 精确命中报告根 span 的现代路径）。
- **api.py 快路径根 span 退出补齐**：与 ReAct 路径 `_stream_graph` 对齐——捕获 `_root_obs`、退出前 `update(metadata={"report_markdown": ...})`（修复快路径 output/metadata 恒 NULL）。
- **不改变**：SSE 事件流、API 响应、报告内容、`_build_trace_output` 的 output 摘要语义（仅补 metadata 与 input.query）。

## Capabilities

### Modified Capabilities

- `trace-observability`: 新增需求「深度分析根 span 携带评估数据（query + report_markdown）」，明确 hosted evaluator 的数据挂载契约。

## Impact

- **代码**:
  - `src/finance_agent/agent_factory.py` — `_stream_graph` 根 span input 加 query、退出 update metadata。
  - `src/finance_agent/api.py` — `_run_graph_streaming` 根 span input 加 query、捕获 `_root_obs` 退出前 update metadata。
- **行为**: 仅 Langfuse 观测层数据丰富；无 Langfuse 时零影响（nullcontext 不变）。
- **契约**: `openspec/specs/trace-observability/spec.md` 经 delta 修改。
- **性能**: 仅在根 span 退出时多写一个 metadata 字段，零额外网络调用。
