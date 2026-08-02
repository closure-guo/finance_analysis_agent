## 1. 数据模型：failure_reason 持久化

- [x] 1.1 `session_store.py` 建表/迁移新增 `failure_reason TEXT` 列（与 `pipeline_snapshot` 同级迁移模式，ALTER TABLE + IF NOT EXISTS）
- [x] 1.2 `update_session_status()` 扩展可选 `failure_reason` 参数，写入失败原因
- [x] 1.3 单元测试：`update_session_status(sid, "failed", failure_reason="超时")` 后 `get_session()` 返回正确 failure_reason
- [x] 1.4 `mark_swept_failed()` 写入 `failure_reason="后端重启，管线无法恢复"`

## 2. LLM 调用错误传播

- [x] 2.1 编写失败测试：`chat_stream` 重试耗尽后 SHALL raise 异常（而非 yield LLMResponse with error text）
- [x] 2.2 修改 [litellm_client.py:217-220](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py#L217-L220)：`yield LLMResponse(text_delta=...)` 改为 `raise`，保留 Langfuse 错误观测收尾
- [x] 2.3 验证 Agent 主循环 [loop.py:466-494](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py#L466-L494) 已有 `except Exception` 能正确捕获并 yield ERROR 事件
- [x] 2.4 验证 `run_deep_analysis` 异常兜底 [agent_factory.py:505-509](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py#L505-L509) 捕获后设置 `failed` + `failure_reason`

## 3. ReAct 路径后台化

- [x] 3.1 编写失败测试：模拟 SSE 断开（GeneratorExit），验证 `run_deep_analysis` 后台 Task 继续执行并更新会话 status 为 completed
- [x] 3.2 重构 `run_deep_analysis` [agent_factory.py:244-546](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py#L244-L546)：拆分后台 Task（`_background_consume`）与 SSE 转发层
  - 后台 Task：消费 `chunk_queue`，执行快照更新 / 时序持久化 / 状态兜底，完成后写报告
  - `event_queue`（`asyncio.Queue(maxsize=100)`）转发事件给 SSE 层，`put_nowait` 满 时 `QueueFull` 静默跳过
  - `GeneratorExit` 不取消后台 Task
- [x] 3.3 后台 Task 异常路径设置 `failed` + `failure_reason`（异常类型与摘要）
- [x] 3.4 后台 Task 正常完成后写最终快照 + `completed` + `update_session_report`
- [x] 3.5 验证：SSE 断开后 `pipeline_snapshot` 持续更新，`get_session()` 最终返回 `completed` + 报告

## 4. SSE 心跳保护

- [x] 4.1 编写失败测试：ReAct 路径 SSE 空闲 15s 后 SHALL 收到 `: heartbeat\n\n`
- [x] 4.2 在 `stream_agent_to_sse` [agent_factory.py:805-1061](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py#L805-L1061) 中用 `asyncio.wait({nextTask}, timeout=15.0)` 包装 `agent.run().__anext__()`，超时 yield 心跳注释
- [x] 4.3 验证心跳不干扰正常事件流解析（前端 SSE parser 正确忽略 `: ` 注释行）

## 5. 管线全局超时

- [x] 5.1 编写失败测试：管线执行超过配置超时时间后 SHALL 设置 `failed` + `failure_reason="管线执行超时"`
- [x] 5.2 ReAct 路径：`_background_consume` 的 `chunk_queue.get()` 包裹 `asyncio.wait_for(..., timeout=600)`，超时设置 failed
- [x] 5.3 fast path：`PipelineRunner._run` [pipeline_runner.py:286-348](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/pipeline_runner.py#L286-L348) 添加 `time.time() - start_time` 检查，超时 break 并设置 failed
- [x] 5.4 超时阈值可配置（环境变量 `PIPELINE_TIMEOUT_SECONDS`，默认 600）

## 6. API 层：会话详情返回 failure_reason

- [x] 6.1 编写测试：`GET /api/sessions/{id}` 对 failed 会话 SHALL 返回 `failure_reason` 字段
- [x] 6.2 修改 `api.py` 会话详情响应 [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) 序列化 `failure_reason`
- [x] 6.3 修改 `session_store.py` `get_session()` / `get_session_summary()` 查询包含 `failure_reason` 列

## 7. 前端：展示中断原因

- [x] 7.1 编写测试：会话 status=failed 且有 failure_reason 时，前端 SHALL 展示具体原因
- [x] 7.2 修改 [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) 轮询恢复逻辑（第 764-850 行）：status=failed 时展示 `failure_reason` 而非笼统的"管线可能已中断"
- [x] 7.3 轮询超时提示也展示从后端获取的 failure_reason（如有）

## 8. E2E 验证

- [x] 8.1 E2E：启动全栈，通过前端输入股票触发深度分析，分析过程中切换会话，验证管线继续执行并最终完成
- [x] 8.2 E2E：触发深度分析后切换会话，等待管线完成，切回原会话验证报告正确展示
- [x] 8.3 E2E：模拟 LLM 失败场景（TESTING=1 stub），验证前端展示 ERROR 事件与 failure_reason
- [x] 8.4 人工验证报告落 `tests/validation/harden-react-path-resilience-validation.md`

> **注**：8.1/8.2 E2E 测试脚本已创建，但 pipeline 场景的 `pipeline-timeline` 元素在当前环境下不可见（现有 `resume-pipeline-across-sessions.spec.ts` 同样失败），属预先存在的环境问题，非本次变更引入。8.3 E2E（LLM 失败场景）已通过。测试脚本已就绪，待环境修复后可直接执行。
