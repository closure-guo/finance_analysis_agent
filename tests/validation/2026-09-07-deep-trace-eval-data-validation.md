# 验证报告: deep-trace-eval-data

**日期**: 2026-09-07
**验证人**: [agent]（单测 + 真实 Langfuse/ClickHouse 持久化验证）
**关联 delta**: openspec/changes/deep-trace-eval-data/
**前置**: Langfuse 已升级 3.205.1 → 3.225.7（trace 数据完好：16252 traces / 22082 observations）

## 验证范围

deep_analysis 根 span 携带评估数据：`input.query`（用户查询/兜底）+ `metadata.report_markdown`（完整报告），两条入口（ReAct 工具路径 `_stream_graph`、快路径 `_run_graph_streaming`）行为一致。

## 单元测试（tests/test_deep_trace_root.py，新增 4 项）

| 用例 | 断言 | 结果 |
|---|---|---|
| TestStreamGraphEvalData::test_input_has_query_fallback | 无 query 时 input 含兜底 `深度分析 贵州茅台(600519)` | ✅ |
| TestStreamGraphEvalData::test_metadata_has_report_markdown | 退出时 metadata.report_markdown = 完整报告 | ✅ |
| TestStreamGraphEvalData::test_no_langfuse_no_crash | Langfuse 未配置不抛异常 | ✅ |
| TestRunGraphStreamingEvalData::test_input_has_query | 快路径 input 含 `req.query` | ✅ |
| TestRunGraphStreamingEvalData::test_metadata_has_report_markdown | 快路径退出时 metadata.report_markdown | ✅ |
| TestRunGraphStreamingEvalData::test_no_langfuse_no_crash | Langfuse 未配置不抛异常 | ✅ |

回归：`tests/test_deep_trace_root.py tests/data/ tests/test_langfuse_tracing.py` → 61 passed；ruff clean；mypy langfuse_tracing 无问题。

## 真实持久化验证（Langfuse 3.225.7 + ClickHouse）

**1. input.query 真实落库**（TESTING stub 跑 `_stream_graph`，真实 langfuse 客户端写 ClickHouse）：

```
trace input = {"stock_code": "600519", "query": "深度分析 贵州茅台(600519)"}
```
兜底查询串端到端生效。✓

**2. metadata.report_markdown 完整内容持久化**（模拟 `_stream_graph` 的「退出前 update」模式跑真实 SDK，写 ClickHouse）：

```
observations metadata = {'report_markdown': '# 贵州茅台验证报告\n完整正文：…'}
```
完整报告正文经 root span update（before-exit）真实持久化，未被 Langfuse 丢弃。✓

## 已知限制（与本 delta 无关）

TESTING stub 管线在当前工作区**无法跑完整程到 final_report**——`compute_metrics` 在 `_find_indicator` 处 KeyError（stub `financial_indicators` 缺 `日期` 列），属并行会话（surgical-citation-repair/ehr-style-claim-direction）改动引入的既有问题，`test_pipeline_stub.py` 有 2 个既有失败可证。故报告正文的「管线内真实产出 → metadata」链条由单测（断言 update 收到 final_report 值）+ SDK 持久化验证（断言完整内容落 ClickHouse）组合覆盖。

## 结论

两条入口的根 span 均携带 `input.query` + `metadata.report_markdown`，真实 Langfuse 持久化验证通过。hosted evaluator 前置数据缺口闭合：`{{query}}` 绑 `input.query`、`{{report}}` 绑 `metadata.report_markdown`（jsonSelector）、filter 用 `metadata contains report_markdown` + `isRootObservation` 即可命中报告根 span。
