# Design: deep-trace-eval-full-data

## 现状

| 模板变量 | 源状态键 | 根 span 现状 |
|---|---|---|
| `analyst_reports` | `analyst_reports: dict[str, AnalystReport]` | output 只有 200 字摘要（`_build_trace_output` 截断章） |
| `debate_history` | `debate_history: list[DebateMessage]`（reducer 追加） | 根 span 无 |
| `research_manager_decision` | `research_manager_conclusion` | 根 span 无 |
| `risk_judgment` | `final_trade_decision`（risk_judge 裁决） | 根 span output 有（键名不匹配模板变量） |
| `trade_decision` | `final_trade_decision` | output ✓（复用） |
| `fund_manager_decision` | `fund_manager_decision` | output ✓（复用） |

## 方案

### 1. 共享 helper（langfuse_tracing.py）

```python
def build_eval_metadata(accumulated: dict) -> dict:
    """从管线累积状态构造根 span metadata 的评估数据段。"""
    md = {"report_markdown": accumulated.get("final_report", "")}
    reports = accumulated.get("analyst_reports") or {}
    if reports:
        md["analyst_reports"] = {
            k: v.model_dump() if hasattr(v, "model_dump") else v
            for k, v in reports.items()
        }
    history = accumulated.get("debate_history") or []
    if history:
        md["debate_history"] = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in history
        ]
    if accumulated.get("research_manager_conclusion"):
        md["research_manager_decision"] = accumulated["research_manager_conclusion"]
    if accumulated.get("final_trade_decision"):
        md["risk_judgment"] = accumulated["final_trade_decision"]
    return md
```

- 缺口省略（spec：缺字段不造）
- Pydantic v2 `model_dump()` 递归序列化 claims（list[Claim]）

### 2. `_stream_graph`（agent_factory.py）

- 累积键增加：`debate_history`（list extend：每次 update 是 `[msg]` 新增一条）、`research_manager_conclusion`（覆盖）
- finally 退出：`_root_obs.update(output=..., metadata=build_eval_metadata(_local_acc))`

### 3. api 快路径（api.py）

- finally 退出：`_root_obs.update(metadata=build_eval_metadata(accumulated))`
- `accumulated` 经 `_merge_update` 已含 debate_history 追加（api.py:566-572 既有逻辑），无需改累积

## 边界

- 无 Langfuse（`_lf is None`）：nullcontext，零影响
- `_build_trace_output` 的 output 摘要语义不动（metadata 与 output 职责分离：output=摘要给人看，metadata=全量给 evaluator）
- trade_decision/fund_manager_decision 已在 output，不重复入 metadata（防 trace 膨胀）
- metadata 增大约 20-50KB（4 分析师全量 markdown+claims + 辩论记录）；既有 trace observation 已容纳 ~300KB state，增量可控，Langfuse metadata 为 Map 列无硬限