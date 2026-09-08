# Proposal: deep-trace-eval-full-data

## Why

deep-trace-eval-data 只把 `query` + `report_markdown` 放到了 deep_analysis 根 span 的 input/metadata。四个 hosted evaluator 模板的其余变量在根 span 上**不可绑定**（源码 + ClickHouse 实测）：

- `analyst_reports`：根 span output 只有 200 字摘要（`_build_trace_output` 截断），decision_grounding/consistency 需核对 claim 出处，摘要不够
- `debate_history`（多空辩论记录）：根 span 完全无此数据
- `research_manager_decision`（RM 结论）：根 span 无
- `risk_judgment`（Risk Judge 裁决 = final_trade_decision）：根 span 无（output 有 final_trade_decision 但模板变量名不匹配且 metadata 无）

导致这四个评审 evaluator 中只有 report_relevance 能完整配置；其余三个绑出来是空值/摘要，评分无意义。

## What Changes

- 新增共享 helper `build_eval_metadata(accumulated)`（langfuse_tracing.py）：从管线累积状态构造 root span metadata 的**评估数据段**，包含：
  - `report_markdown`（既有）
  - `analyst_reports`（**全量**序列化：summary/key_findings/claims/markdown，Pydantic model_dump）
  - `debate_history`（全量多空辩论消息列表）
  - `research_manager_decision`（RM 结论，源键 `research_manager_conclusion`）
  - `risk_judgment`（Risk Judge 裁决 = `final_trade_decision`）
- **两条入口 checkout 对齐**：`_stream_graph`（ReAct 路径）与 `_run_graph_streaming`（api 快路径）退出时都以 `build_eval_metadata` 更新根 span metadata，替代现有内联 `{"report_markdown": ...}`。
- `_stream_graph` 的 `_local_acc` 增加累积 `debate_history`（list 追加语义）、`research_manager_conclusion`。
- **不改变**：SSE 事件流、API 响应、报告内容、`_build_trace_output` 的 output 摘要语义。

## Capabilities

### Modified Capabilities

- `trace-observability`: 扩展「深度分析根 span 携带评估数据」需求——metadata 除 `report_markdown` 外须含 `analyst_reports`（全量）/`debate_history`/`research_manager_decision`/`risk_judgment`，支撑四个 hosted evaluator 模板变量绑定。

## Impact

- **代码**:
  - `src/finance_agent/langfuse_tracing.py` — 新增 `build_eval_metadata`。
  - `src/finance_agent/agent_factory.py` — `_stream_graph` 累积新键 + 退出用 helper。
  - `src/finance_agent/api.py` — `_run_graph_streaming` 退出用 helper。
  - `tests/test_deep_trace_root.py` — 新增断言（metadata 含全量评估字段）。
- **行为**: 仅 Langfuse 观测层 metadata 丰富；无 Langfuse 零影响。
- **契约**: `openspec/specs/trace-observability/spec.md` 经 delta 修改。（MODIFIED 场景）
- **性能**: metadata 增加 ~20-50KB（全量分析师报告+辩论记录），换取 evaluator 可评完整内容；既有 trace 已容纳 ~300KB state 摘要，增量可控。