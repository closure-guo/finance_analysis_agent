# Tasks: deep-trace-eval-data

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/test_deep_trace_root.py`（或新建）新增：`_stream_graph` 根 span `input` 含 `query`（mock langfuse + fake graph）
- [x] 1.2 `_stream_graph` 退出时根 span `update(metadata={"report_markdown": ...})`（final_report 写入）
- [x] 1.3 `_stream_graph` 无 query 时 input 含兜底 `深度分析 {stock_name}({stock_code})`
- [x] 1.4 api.py `_run_graph_streaming` 根 span `input` 含 `req.query`
- [x] 1.5 api.py 快路径退出时 `update(metadata={"report_markdown": ...})`
- [x] 1.6 无 Langfuse（get_langfuse=None）两条路径均不抛异常

## 2. 实现

- [x] 2.1 `_stream_graph`：根 span input 增加 `query`（`initial_state.get("query")` 或兜底串）；finally 内、`__exit__` 前 `_root_obs.update(output=..., metadata={"report_markdown": _local_acc.get("final_report","")})`
- [x] 2.2 `run_deep_analysis`：initial_state 无需 query（兜底由 `_stream_graph` 处理），如便于测试可在工具闭包透传
- [x] 2.3 api.py `_run_graph_streaming`：根 span input 增加 `query`（`req.query` 或兜底）；捕获 `_root_obs = _root_cm.__enter__()`，finally 内退出前 `update(metadata={"report_markdown": accumulated.get("final_report","")})`

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/test_deep_trace_root.py` 全绿
- [x] 3.2 `uv run ruff check src/finance_agent/agent_factory.py src/finance_agent/api.py` + 新增测试
- [x] 3.3 `uv run mypy src/finance_agent/agent_factory.py src/finance_agent/api.py`（既有容忍项除外）
- [x] 3.4 真实验证：跑一次深度分析（TESTING stub 或真实），查 ClickHouse 根 span metadata.report_markdown + input.query，落 `tests/validation/`
- [x] 3.5 `openspec validate --strict deep-trace-eval-data`
- [x] 3.6 archive 前 tasks 全勾 + 门禁通过
