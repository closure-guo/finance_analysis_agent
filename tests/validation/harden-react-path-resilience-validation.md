# harden-react-path-resilience 人工验证报告

| 字段 | 值 |
|------|-----|
| 变更 | harden-react-path-resilience |
| 日期 | 2026-07-30 |
| 验证人 | Agent |
| 状态 | 待人工确认 |

## 变更概述

解决两个核心问题：
1. **会话切换导致 agent 任务中断**：ReAct 路径的 `run_deep_analysis` async generator 与 SSE 绑定，SSE 断开时管线中断。改为后台 Task 独立执行，SSE 断开后管线继续。
2. **管线不明原因中断**：LLM 失败静默 yield 错误文本、无心跳保护、无全局超时、中断原因不可见。

## 验证项目

### 1. failure_reason 持久化（第 1 组）

| 测试 | 结果 |
|------|------|
| `test_failure_reason_roundtrip` | ✅ 通过 |
| `test_failure_reason_default_none` | ✅ 通过 |
| `test_failure_reason_overwrite` | ✅ 通过 |

验证内容：`update_session_status(sid, "failed", failure_reason="超时")` 后 `get_session()` 返回正确 failure_reason；`mark_swept_failed()` 写入"后端重启，管线无法恢复"。

### 2. LLM 调用错误传播（第 2 组）

| 测试 | 结果 |
|------|------|
| `test_chat_stream_raises_on_retry_exhausted` | ✅ 通过 |
| `test_chat_stream_retries_before_raising` | ✅ 通过 |

验证内容：`chat_stream` 重试耗尽后 raise 异常而非 yield 错误文本；Agent 主循环 `except Exception` 捕获并 yield ERROR 事件。

### 3. ReAct 路径后台化（第 3 组）

| 测试 | 结果 |
|------|------|
| `test_generator_close_does_not_abort_pipeline` | ✅ 通过 |
| `test_generator_close_pipeline_snapshot_persisted` | ✅ 通过 |
| `test_pipeline_failure_sets_failure_reason` | ✅ 通过 |

验证内容：SSE 断开（aclose）后后台 Task 继续执行，会话最终为 completed；快照持续更新；异常路径设置 failed + failure_reason。

### 4. SSE 心跳保护（第 4 组）

| 测试 | 结果 |
|------|------|
| `test_sse_heartbeat_on_idle` | ✅ 通过 |
| `test_sse_heartbeat_does_not_interfere_events` | ✅ 通过 |

验证内容：SSE 空闲超过 heartbeat_interval 后收到心跳注释；心跳不干扰正常事件流。

### 5. 管线全局超时（第 5 组）

| 测试 | 结果 |
|------|------|
| `test_pipeline_timeout_sets_failed` | ✅ 通过 |

验证内容：管线超过 `PIPELINE_TIMEOUT_SECONDS` 后设置 failed + failure_reason="管线执行超时"。

### 6. API 层返回 failure_reason（第 6 组）

| 测试 | 结果 |
|------|------|
| `test_session_detail_returns_failure_reason` | ✅ 通过 |
| `test_session_detail_failure_reason_none_when_not_set` | ✅ 通过 |
| `test_session_list_returns_failure_reason` | ✅ 通过 |

验证内容：`GET /api/sessions/{id}` 对 failed 会话返回 failure_reason 字段；`list_sessions()` 也包含该字段。

### 7. 前端展示中断原因（第 7 组）

验证内容：
- `App.tsx` 轮询恢复逻辑：status=failed 时展示 `failure_reason` 而非笼统的"管线可能已中断"
- 轮询超时提示也尝试从后端获取 failure_reason
- TypeScript 编译通过（`tsc --noEmit` 无错误）

### 8. E2E 验证（第 8 组）

| 测试 | 结果 |
|------|------|
| `8.1 切换会话后管线后台继续执行并最终完成` | 脚本已创建，预先存在环境问题阻止执行 |
| `8.2 切换会话后等待完成，切回验证报告展示` | 脚本已创建，预先存在环境问题阻止执行 |
| `8.3 LLM 失败场景展示 failure_reason` | ✅ 通过 |

E2E 测试脚本位于 `tests/e2e/playwright/tests/harden-react-path-resilience.spec.ts`，配置文件 `tests/e2e/playwright/playwright.resilience.config.ts`。

**8.3 通过说明**：STUB_SCENARIO=llm_failure 下，LLM 调用 raise RuntimeError，Agent 主循环捕获并 yield ERROR 事件，api.py 发送 error SSE，前端正确展示错误消息。

**8.1/8.2 环境问题说明**：pipeline 场景的 `pipeline-timeline` 元素在当前环境下不可见。后端日志确认 `POST /api/analyze` 返回 200 OK，说明请求到达后端。但前端未渲染管线时间轴。现有 `resume-pipeline-across-sessions.spec.ts` 在相同环境下同样失败，确认是预先存在的环境问题，非本次变更引入。

## 单元/集成测试汇总

```
20 passed in 22.09s
```

## 已知限制

- Agent 编排整体后台化（`agent.run()` 之后的总结步骤仍与 SSE 绑定）属 Non-Goal
- Langfuse Context 跨 async generator 边界问题未修复（incident 008 警告级）
- 管线并行化重构属架构性大改，不在本次范围
- 后端重启后后台 Task 丢失（与 PipelineRunner 一致，由 mark_swept_failed 覆盖）
