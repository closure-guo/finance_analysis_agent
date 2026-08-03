## 1. 后端：per-run 终态事件去重

- [x] 1.1 编写失败测试：同一会话两轮 `publish` 终态事件，第二轮不被吞。测试创建 `StreamRegistry`，第一轮 `start()` + `publish(done)` 后 `_run_task` 结束注销，第二轮 `start()` + `publish(done)`，断言第二轮返回非 0 seq 且事件写入 journal。覆盖 `done`/`interrupted`/`error` 三种终态类型。
- [x] 1.2 编写失败测试：同一轮运行内重复终态事件去重。第一轮 `publish(done)` 后再次 `publish(done)`，断言第二次返回 0（同轮内去重生效）。
- [x] 1.3 `SessionStream` dataclass 新增 `terminalPublished: bool = False` 字段（`stream_registry.py`）。
- [x] 1.4 `publish()` 终态 CAS 改为检查 `stream.terminalPublished`：已为 True 则返回 0，否则置 True 后正常写入。移除 `has_terminal_event` 调用。同步给 `_publish_sync()`（cancel 路径）加同样的 CAS，避免 interrupted 重复写入。
- [x] 1.5 全局搜索 `has_terminal_event` 调用方；仅 `publish` 调用，但 `get_terminal_event` 仍在用 -> 保留 `has_terminal_event` 函数（cancel 幂等等潜在用途）与其测试，仅移除 `publish` 中的调用。
- [x] 1.6 修正 `test_chat_single_flight_rejects_second_request` 的竞态：原测试用"读首事件即断开"，但首事件要等 stub sleep 5s 后才到达，此时任务已跑完，断言恰好落在任务注销窗口上（旧代码靠 `has_terminal_event` 的 DB 扫描延迟偶然通过）。改为后台 task 持续消费 + `sleep(1.0)` 在 stub 窗口内断言，与同文件 cancel 测试模式一致。
- [x] 1.7 运行 `uv run pytest tests/test_terminal_cas.py tests/test_stream_registry.py tests/test_react_resumable.py tests/test_followup_sse_termination.py tests/test_subscribe_order.py tests/test_fastpath_bridge.py tests/test_session_store_terminal.py` 确认相关测试全通过。

## 2. 前端：chat_done 路由对齐

- [x] 2.1 编写 Vitest：`chat_done` 抵达时游标消失且 thinking item 收口（`frontend/src/test/streamingCursorLifecycle.test.ts`）。
- [x] 2.2 在 `startAnalysis` SSE 循环中补齐 `chat_done` 分支，路由到 `handleChatStreamEvent(event, assistantMsgIdRef.current)`，与 `quickChat` 对齐（`App.tsx`）。
- [x] 2.3 运行 `cd frontend && npm test` 确认前端测试全通过。

## 3. 前端：流结束防御性清理

- [x] 3.1 编写 Vitest：模拟 SSE 流在缺少 `done` 的情况下结束，断言游标消失；覆盖空流、幂等重复清理、AbortError 不清游标。
- [x] 3.2 在 `startAnalysis` 的 reader-done 防御性清理点，追加将 `assistantMsgIdRef.current` 对应消息 `streaming` 置 false。
- [x] 3.3 在 `startAnalysis` 的 catch 块追加同样的 `streaming: false` 清理（AbortError 提前 return，不清当前视图消息）。
- [x] 3.4 运行 `cd frontend && npm test` 确认前端测试全通过（147 passed）。

## 4. 验证

- [x] 4.1 运行 `uv run ruff check` 与 `uv run mypy` 确认后端 lint 与类型检查通过。
- [x] 4.2 运行 `cd frontend && npm test` 确认前端全通过（17 files / 147 tests）。
- [x] 4.3 确认全量 `uv run pytest` 的失败均为 pre-existing：(a) `test_5layer_pipeline.py` 的 Fund Manager 决策枚举断言（`assert 'return' in ('approve','reject','revise')`），已用 git stash 隔离验证改动前以相同断言失败；(b) 约 87 个 `Runner.run() cannot be called from a running event loop`，为并跑时事件循环隔离问题，涉及未触碰文件，单独运行全部通过。
- [x] 4.4 人工验证：启动全栈，执行两轮深度追问 + 一轮"再分析一只股票"触发二次管线，确认第二轮游标正常消失。验证报告落 `tests/validation/fix-terminal-event-dedup-scope-validation.md`。
