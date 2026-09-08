# Design: deep-trace-eval-data

## 现状（实测 ClickHouse）

两条 deep_analysis 入口的根 span：

| 入口 | 根 span input | 根 span output | 根 span metadata |
|---|---|---|---|
| ReAct 工具路径 `_stream_graph`（agent_factory.py:901） | `{"stock_code": ...}` | `_build_trace_output`（报告前 500 字摘要） | 无 |
| 快路径 `_run_graph_streaming`（api.py:974） | `{"stock_code": ...}` | NULL（退出从不 update） | 无 |

用户查询：快路径有 `req.query`（AnalyzeRequest.query）；ReAct 工具签名只有 `stock_code/stock_name`（LLM 只传这俩），无真实查询文本。

## 方案

### 1. 根 span input 增加 query

```
_stream_graph（agent_factory.py）:
    _query = initial_state.get("query") or f"深度分析 {_stock}"   # _stock = stock_name or stock_code
    input={"stock_code": ..., "query": _query}

_run_graph_streaming（api.py）:
    _query = (req.query or "").strip() or f"深度分析 {stock_name_display}"
    input={"stock_code": stock_code, "query": _query}
```

ReAct 路径的 query 兜底串 `深度分析 {stock_name}({stock_code})` 语义 =「本次分析对象」，作为报告切题度的查询表示可接受（报告本身就是对该股票的分析）。

### 2. 根 span metadata 增加 report_markdown（退出前）

```
_stream_graph finally（现有 update(output=...) 处扩展）:
    _root_obs.update(
        output=_build_trace_output(_local_acc),
        metadata={"report_markdown": _local_acc.get("final_report", "")},
    )

_run_graph_streaming finally:
    # 现为裸 __exit__，需先捕获 _root_obs = _root_cm.__enter__()
    _root_obs.update(metadata={"report_markdown": accumulated.get("final_report", "")})
```

- 更新时机在 `__exit__` 之前（content-fidelity 已修复「post-exit update 被 Langfuse v4 丢弃」的坑，必须保持 before-exit）。
- `_local_acc` / `accumulated` 在流式期间已累积 final_report（两路径均如此）。

### 3. hosted evaluator 消费契约

- 变量映射：`{{query}}` ← `input` + jsonSelector `query`；`{{report}}` ← `metadata` + jsonSelector `report_markdown`（Langfuse 3.225.7 变量映射支持 jsonSelector，源码 `observationVariableMapping` 已验证）。
- filter：`metadata` contains `report_markdown` + `isRootObservation` = true → 精确命中报告根 span，observation evaluator 现代路径。
- 兜底查询串保证 `input.query` 恒非空，judge 不会因空查询判分异常。

## 边界

- Langfuse 未配置（`_lf is None`）：两条路径保持 nullcontext，零影响、不抛异常。
- api.py 快路径 output 保持现状（NULL→不改，避免循环导入 `_build_trace_output` 的风险）；evaluator 走 metadata，不依赖 output。
- `_stream_graph` 的 output 逻辑不动（`_build_trace_output` 摘要语义保留），仅附加 metadata。
