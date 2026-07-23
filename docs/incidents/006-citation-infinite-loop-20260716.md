# 006: 深度模式无响应 — citation 重试无限循环

**日期**: 2026-07-16
**状态**: 已修复
**触发**: 用户反馈"深度模式，输入后无响应"

---

## 问题描述

深度模式输入股票（如"茅台"）后，管线进度卡在 `技术面分析 → 引用校验` 反复循环，永不进入辩论/报告阶段，前端长时间无最终结果（或连接被静默关闭）。

通过 SSE 诊断脚本（`tests/scripts/diag_deep_sse.py`）直连后端观察到：

- PREP（check_cache / fetch_data / validate / compute_metrics）正常
- `technical_analyst` → `verify_citations` 后，`after_citation` 路由回 `retry` → 再次 `technical_analyst` → `verify_citations` …
- 循环 5+ 次（260s+）仍不停止，从未到达 `bull_r1`/`bear_r1`（Layer II）
- 首次复现还在 ~114s 出现 `peer closed connection`（服务端静默关闭，无 error/done 事件）

---

## 根因分析

### 1. 主因：`iteration_count` 从不递增 → 重试上限失效

`routing.after_citation` 的重试守卫：

```python
def after_citation(state):
    if state.get("citation_pass", False):
        return "render"
    if state.get("iteration_count", 0) < 3:   # 读取
        return "retry"
    return "render"
```

`state.py` 声明了 `iteration_count: int  # 重试次数（上限 3）`，`after_citation` 也读取它，但 **`verify_citations` 节点只返回 `citation_report` + `citation_pass`，从不递增 `iteration_count`**。

因此 `iteration_count` 恒为 0，`0 < 3` 永真 → `citation_pass=False` 时无限 `retry`，图永远无法推进到辩论/报告。

### 2. citation_pass 长期为 False 的诱因

`verify_claims` 对 LLM 产出的 Claim 做确定性校验：`field_ref` 路径在 state 中解析不到即判 FAIL，`all_passed = (failed == 0)`。`deepseek-v4-pro`（`reasoning_effort=max`）产出的 Claim 的 `field_ref` 常与 state schema 路径不完全匹配，导致至少一条 FAIL → `citation_pass=False` → 触发主因的无限重试。

### 3. 次因：SSE 流异常被静默关闭

`/api/analyze` 的 `async for sse_str in stream_agent_to_sse(...)` 外层无 try/except。`stream_agent_to_sse` 自身（Langfuse `start_as_current_observation` 上下文、`on_metadata` 回调等）抛出的异常会越过 `agent.run` 的 `except Exception`，直接终止生成器 → Starlette 关闭连接，前端收不到 error/done，无限等待。

> 注：日志中 `ModuleNotFoundError: Please install langchain`（Langfuse CallbackHandler 不可用）与 `Context error: No active span` 为可观测性噪声，已被各自 `try/except` 兜住，非本次主因。

---

## 修复方案

| # | 文件 | 修改 |
|---|------|------|
| 1 | `nodes/citation_node.py` | `verify_citations` 返回 `iteration_count = state.get("iteration_count", 0) + 1`，使 `after_citation` 的 `< 3` 上限真正生效 |
| 2 | `api.py` | `stream_agent_to_sse` 消费外层加 `try/except Exception`：异常时发送 `error` 事件并置 `stream_error`，跳过 `awaiting_input`，最后仍发 `done`，避免前端无限等待 |
| 3 | `tests/nodes/test_citation_node.py` | 新增 `test_increments_iteration_count`、`test_retry_loop_terminates_after_max` 回归测试（旧代码下 `result["iteration_count"]` 直接 KeyError） |

---

## 端到端验证（修复后）

`tests/scripts/diag_deep_sse.py "茅台"` 实测：

- `technical_analyst → verify_citations` 共 **3 次**（iteration_count 1/2/3），第 3 次后 `after_citation` 返回 `render`
- 进入 Layer II：`bear_r1`/`bull_r1`(204s) → `bull_r2`/`bear_r2` → `research_manager` → `trader`(Layer III) → 风控 R1/R2 → `risk_judge` → `fund_manager`(Layer V) → `generate_report` → `generate_file`
- 终止事件：`report_ready`（完整贵州茅台投研报告）+ `chat_done` + `done`，`terminal event seen: True`，总耗时 295s

回归测试：`test_citation_node.py` + `test_routing.py` 共 19 项全绿；`ruff check` 通过。

---

## 关联

- ADR-0011 五层架构（citation retry 路由的设计来源）
- [005](005-garp-dupont-test-pollution-20260604.md) 同属"LLM 产出 → 确定性校验"链路的可靠性问题
