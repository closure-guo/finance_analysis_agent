# Tasks: deep-trace-eval-full-data

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/test_deep_trace_root.py` 新增 `TestStreamGraphEvalFullData`：mock graph 产出 `debate_history` + `research_manager_conclusion` + `final_trade_decision` + 全量 `analyst_reports`（真实 Pydantic 对象），断言退出时根 span metadata 含四键
- [x] 1.2 断言 `metadata.analyst_reports` 含每分析师 `markdown` 全文（非摘要）
- [x] 1.3 断言 `metadata.debate_history` 是消息列表（多轮累加）
- [x] 1.4 缺字段不造：accumulated 无 debate_history 时 metadata 无该键、不抛异常
- [x] 1.5 api 快路径 `_run_graph_streaming` 退出时 metadata 含新四键（回归 1.5 复用）
- [x] 1.6 `report_markdown` 仍存在（deep-trace-eval-data 回归）

## 2. 实现

- [x] 2.1 `langfuse_tracing.py` 新增 `build_eval_metadata(accumulated) -> dict`：report_markdown + analyst_reports(model_dump) + debate_history(model_dump list) + research_manager_decision + risk_judgment，缺口省略
- [x] 2.2 `_stream_graph`：`_local_acc` 累积键增加 `debate_history`（list extend 语义）、`research_manager_conclusion`；退出 update 改用 `build_eval_metadata(_local_acc)`
- [x] 2.3 api `_run_graph_streaming`：退出 update 改用 `build_eval_metadata(accumulated)`（快路径 accumulated 经 _merge_update 已含 debate_history 等）

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/test_deep_trace_root.py` 全绿
- [x] 3.2 `uv run ruff check` + 相关回归（tests/test_langfuse_tracing.py 等）
- [x] 3.3 真实验证：SDK 模式验证 metadata 含全量评估段持久化到 ClickHouse（复用 deep-trace-eval-data 验证法），落 `tests/validation/`
- [x] 3.4 `openspec validate --strict deep-trace-eval-full-data`
- [x] 3.5 archive 前 tasks 全勾 + 门禁通过