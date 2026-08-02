## Context

当前系统有两条深度分析执行路径：

- **fast path**（`/api/analyze` 带 `stock_code`）：`PipelineRunner.start()` 启动独立 daemon 线程，SSE 端通过 `get_events()` 轮询事件队列。SSE 断开后管线继续执行，快照持续持久化。
- **ReAct 路径**（自然语言输入，真实 UI 唯一可达路径）：`run_deep_analysis` 工具是 async generator，`graph.stream` 在 executor 线程运行，通过 `asyncio.Queue` 跨线程传递事件。`stream_agent_to_sse` 直接 `async for` 消费 Agent 的事件流，SSE 与 Agent 编排绑定。

`pipeline-events/spec.md` 第 21 行已明确标注 ReAct 路径后台化为"后续 change"。本次 change 正是兑现该承诺。

此外，LLM 调用失败时 `chat_stream` yield 错误文本而非 raise（[litellm_client.py:217-220](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py#L217-L220)），Agent 主循环将其当作正常最终回复处理（[loop.py:492-494](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py#L492-L494)），产生静默失败。ReAct 路径的 SSE 也缺乏心跳保护（对比 fast path 的 `": heartbeat\n\n"`，[api.py:1004-1006](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L1004-L1006)），长时间无事件时代理/浏览器可能断连。

## Goals / Non-Goals

**Goals:**

- ReAct 路径 `run_deep_analysis` 工具内的 `graph.stream` 后台化：SSE 断开后管线继续执行，结果与快照持久化到会话
- LLM 调用重试耗尽后 raise 异常，杜绝静默失败
- ReAct 路径 SSE 流增加心跳保护
- 管线全局超时 + `failure_reason` 持久化，前端展示具体中断原因

**Non-Goals:**

- Agent 编排整体后台化（`agent.run()` 之后的总结步骤仍与 SSE 绑定；`run_deep_analysis` 完成后 Agent 通常仅生成简短摘要，中断影响小）
- Langfuse Context 跨 async generator 边界问题修复（incident 008 记录的警告级问题，不阻断功能）
- 管线并行化重构（Layer II/IV 串行 LLM 调用耗时问题，属架构性大改）
- 断点续跑（管线中断后从中间节点恢复执行），本次仅做"后台跑到底" + "中断后标记 failed"

## Decisions

### 决策 1：ReAct 路径后台化--分离事件处理与事件转发

**方案**：将 `run_deep_analysis` 内 `graph.stream` 的事件消费拆为两层：

1. **后台 Task**（`asyncio.create_task`）：消费 `chunk_queue`，执行快照更新 / 状态持久化 / 报告写入。SSE 断开后继续运行。
2. **SSE 转发层**（async generator 主体）：从 `event_queue`（`asyncio.Queue(maxsize=100)`）读取事件并 `yield StreamEvent`。SSE 断开时 generator 被关闭，`GeneratorExit` 不传播到后台 Task。

```
graph.stream (executor thread)
    ↓ chunk_queue (跨线程)
_background_consume (asyncio.Task, 独立生命周期)
    ├── 更新快照 → session_store.update_pipeline_snapshot()
    ├── 更新时序 → session_store.update_pipeline_timelines()
    ├── 转发事件 → event_queue.put_nowait() (满则跳过)
    └── 完成后 → update_session_status("completed") + update_session_report()
         ↑ SSE 断开后仍执行
run_deep_analysis generator (async for event_queue)
    ↓ yield StreamEvent
stream_agent_to_sse → SSE
```

**关键点**：

- `event_queue` 设 `maxsize=100`，`put_nowait` 满 时 `QueueFull` 静默跳过--SSE 断开后事件不再转发，但快照/状态仍由后台 Task 持久化
- `GeneratorExit` 在 SSE 转发层被捕获，**不取消**后台 Task
- 后台 Task 完成（正常或异常）后更新会话 status，前端轮询恢复时读取最终状态

**备选方案**：复用 `PipelineRunner`（接受同步生成器）。但 `run_deep_analysis` 的事件流是 async generator（yield `StreamEvent`），且 PipelineRunner 是同步线程模型，适配为 async 需大幅改造。`asyncio.create_task` 更贴合现有 async 架构，改动更小。

### 决策 2：LLM 错误 raise 而非 yield

**方案**：[litellm_client.py:217-220](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py#L217-L220) 的 `yield LLMResponse(text_delta=...)` 改为 `raise`。

Agent 主循环（[loop.py:466-494](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py#L466-L494)）已有的异常处理路径：LLM 异常会传播到 `agent.run()` 的外层 try/except，被捕获后 yield `ERROR` 事件。在 `run_deep_analysis` 路径中，异常传播到后台 Task，设置 `failed` 状态。

**备选方案**：新增 `LLMResponse(is_error=True)` 字段让 Agent 判断。但这需要修改 Agent 主循环的错误判断逻辑，不如直接 raise 直观。

### 决策 3：ReAct 路径心跳--`asyncio.wait` 包装 `__anext__`

**方案**：在 `stream_agent_to_sse` 中用 `asyncio.wait({next_task}, timeout=15.0)` 包装 `agent.run().__anext__()`，超时则 `yield ": heartbeat\n\n"` 并继续等待，不取消正在进行的 `__anext__()`。

```python
agentGen = agent.run(user_input, force_tool=force_tool)
nextTask = asyncio.create_task(agentGen.__anext__())
while True:
    done, _ = await asyncio.wait({nextTask}, timeout=15.0)
    if not done:
        yield ": heartbeat\n\n"
        continue
    try:
        event = nextTask.result()
    except StopAsyncIteration:
        break
    # 处理 event...
    nextTask = asyncio.create_task(agentGen.__anext__())
```

**备选方案**：`asyncio.wait_for` 更简洁，但超时会取消内部 coroutine，可能导致 async generator 状态不一致。`asyncio.wait` 不取消 pending task，更安全。

### 决策 4：全局超时--后台 Task 级 `wait_for`

**方案**：在 `_background_consume` 的 `chunk_queue.get()` 上设 `asyncio.wait_for(..., timeout=600)`（10 分钟）。超时后设置 `failed` + `failure_reason="管线执行超时"`。

PipelineRunner._run（fast path）同步线程中用 `threading.Timer` 或在 `event_source()` 的 for 循环中检查 `time.time() - start_time`。

### 决策 5：`failure_reason` 列--SQLite 迁移

**方案**：`session_store.py` 建表迁移新增 `failure_reason TEXT` 列（与现有 `pipeline_snapshot` 等列同级迁移模式）。`update_session_status` 扩展可选 `failure_reason` 参数。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 后台 Task 在后端重启时丢失（与 PipelineRunner 一致） | `mark_swept_failed` 已覆盖：重启后 running 会话标记 failed，本次新增 failure_reason 记录"后端重启" |
| `event_queue` 满时丢弃事件导致 SSE 消费者断线重连后丢中间事件 | 设计如此：快照已持久化，重连后通过快照恢复完整时间轴，非通过 SSE 重放 |
| `asyncio.wait` 心跳方案增加 stream_agent_to_sse 复杂度 | 封装为独立 helper，保持事件映射循环不变 |
| LLM raise 异常可能破坏现有依赖错误文本的调用方 | Agent 主循环已有 `except Exception` 捕获路径；快速模式 `/api/chat` 同样走 `stream_agent_to_sse`，异常被 api.py 的 `except` 捕获并发送 error SSE |
| `run_deep_analysis` 后台完成后 Agent 编排已中断，报告不会通过 SSE 推送 | 前端轮询恢复逻辑已覆盖：status=completed 时从会话存储读取报告（App.tsx 第 804-838 行） |

## Migration Plan

1. `session_store.py` 新增 `failure_reason` 列（迁移，与 `pipeline_snapshot` 同模式）
2. `litellm_client.py` 改 raise（破坏性，但影响范围可控）
3. `agent_factory.py` `run_deep_analysis` 后台化重构 + `stream_agent_to_sse` 心跳
4. `pipeline_runner.py` 全局超时
5. `api.py` 会话详情返回 `failure_reason`
6. `App.tsx` 前端展示 `failure_reason`
7. 每步配套测试，E2E 验证会话切换不中断管线

**回滚策略**：各改动相互独立，可逐步回滚。`failure_reason` 列新增不影响现有逻辑（可空）；LLM raise 改动可回退为 yield（但会恢复静默失败问题）。

## Open Questions

- 全局超时阈值：10 分钟是否合理？管线平均 4-5 分钟，最长 258s（incident 008），但 AKShare 限频可能更长。需实际测量后确认。
- 后台 Task 完成后是否需要通知前端（如 WebSocket 推送），还是仅依赖轮询？当前前端轮询 2s 间隔已足够，WebSocket 属过度设计。
