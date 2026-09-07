# 验证报告: deep-trace-eval-full-data

**日期**: 2026-09-07
**验证人**: [agent]（单测 + 真实 Langfuse/ClickHouse 持久化验证）
**关联 delta**: openspec/changes/deep-trace-eval-full-data/
**前置**: deep-trace-eval-data（根 span 已落 query + report_markdown）；Langfuse 3.225.7

## 验证范围

deep_analysis 根 span metadata 扩展评估数据段：`analyst_reports`（全量）/`debate_history`/`research_manager_decision`/`risk_judgment`，支撑 debate_quality / decision_grounding / consistency 三个 evaluator 模板变量绑定。

## 单元测试（tests/test_deep_trace_root.py，新增 4 项）

| 用例 | 断言 | 结果 |
|---|---|---|
| TestStreamGraphEvalFullData::test_metadata_has_full_eval_fields | metadata 含 analyst_reports(全量 markdown)/debate_history/research_manager_decision/risk_judgment + report_markdown 回归 | ✅ |
| TestStreamGraphEvalFullData::test_missing_fields_omitted | 缺字段省略不造、不抛异常 | ✅ |
| TestRunGraphStreamingEvalFullData::test_metadata_has_full_eval_fields | api 快路径 metadata 含全量评估段 | ✅ |

回归：`tests/test_deep_trace_root.py tests/test_langfuse_tracing.py` → 26 passed；ruff clean。

## 真实持久化验证（Langfuse 3.225.7 + ClickHouse）

`build_eval_metadata` 构造 metadata（真实 AnalystReport/DebateMessage Pydantic 对象）→ 根 span「退出前 update」→ ClickHouse 实测：

```
metadata keys: analyst_reports / debate_history / report_markdown / research_manager_decision / risk_judgment（5 键全落）
analyst_reports: {"technical": {"agent_name", "summary", "key_findings", "claims", "markdown": "## 技术面完整报告\n全文……"}, "fundamental": {...全量}}
debate_history: [{"role": "bull", "round": 1, "content": "看多论点", ...}, {"role": "bear", ...}]
```

Pydantic `model_dump()` 递归序列化（含 claims）经 Langfuse metadata Map 列完整持久化 ✓

## 结论

四个 evaluator 模板中，除 report_relevance（已可配）外，debate_quality（debate_history）、decision_grounding（analyst_reports + research_manager_decision + trade_decision）、consistency（analyst_reports + research_manager_decision + risk_judgment + fund_manager_decision + report_conclusion）的变量现已全部可在根 span metadata/output 绑定。trade_decision/fund_manager_decision 复用既有 output 字段（不重复入 metadata，防膨胀）。