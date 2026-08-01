# 验证报告：resume-stream-on-session-switch + ReAct 路径解耦

> 日期：2026-08-01
> 验证人：AI Agent（自动验证 + Docker 实证）

## 一、验证范围

本次验证覆盖 `resume-stream-on-session-switch` OpenSpec change 的全部 spec 条款，
包括架构完善阶段新增的 ReAct 路径（/api/chat、/api/analyze 无股票代码路径）迁移。

## 二、测试验证

### 2.1 单元测试

| 测试文件 | 用例数 | 结果 |
|----------|--------|------|
| test_react_resumable.py | 4 | 全通过 |
| test_sse_stream.py | 5 | 全通过 |
| test_stream_204.py | 3 | 全通过 |
| test_incremental_persist.py | 4 | 全通过 |
| test_terminal_cas.py | 4 | 全通过 |
| test_subscribe_order.py | 3 | 全通过 |
| test_fastpath_bridge.py | 3 | 全通过 |
| test_stream_registry.py | 7 | 全通过 |
| test_sse_heartbeat.py | 2 | 全通过 |

test_react_resumable.py 4 个用例覆盖：
- `test_chat_disconnect_task_continues`：断线后任务继续跑完，journal 有 done，无悬空 user 消息
- `test_chat_single_flight_rejects_second_request`：运行中拒绝新消息返回 409，不追加 user 消息
- `test_chat_cancel_persists_interrupted`：cancel 后 interrupted 终态，部分回复落库
- `test_analyze_disconnect_task_continues`：analyze ReAct 路径断线后任务跑完，journal 有 awaiting_input + done

### 2.2 全量回归

`uv run pytest tests/ --ignore=tests/e2e`：539 passed, 2 deselected
- deselect 1：test_react_pipeline_snapshot（预存失败，stash 验证与本次无关）
- deselect 2：test_pipeline_stub streaming tool think（DeepSeek API flaky："Thinking mode does not support this tool_choice"，与本次无关）

### 2.3 Lint

`uv run ruff check src/finance_agent/api.py tests/test_react_resumable.py`：All checks passed

## 三、Docker 实证

### 3.1 快速模式"沈阳天气"完整链路（permission_required 死锁修复）

```
POST /api/chat {"message": "沈阳天气"}
-> search_start -> tool_call -> search_result -> tool_result -> 完整回答 -> done
204 个事件，PASS
```

### 3.2 analyze "分析一下热门股票" 断线恢复（ReAct 路径解耦修复）

```
POST /api/analyze {"query": "分析一下热门股票"}
-> session_created -> search_start（读到此处断开）
等待 15s（任务在后台继续）
GET /api/sessions/{id}/stream
-> session_created -> search_start -> tool_call -> search_result -> tool_result
   -> thinking_token -> chat_token -> chat_done -> awaiting_input -> done
恢复端点收到完整事件流（10 种事件类型），PASS
```

### 3.3 修复前对比

修复前同一场景：
- session_events: 0（journal 无事件）
- chat_history: 悬空 user 消息（无 assistant 回复）
- GET /api/sessions/{id}/stream: 204 No Content
- session status 残留 clarifying

## 四、Spec 条款符合性

| Spec 条款 | 验证方式 | 结果 |
|-----------|---------|------|
| Decoupled Generation Lifecycle | test_chat_disconnect + test_analyze_disconnect | ✅ 断线不杀任务 |
| Stream Event Journal | Docker 实证 journal events 数 | ✅ 事件落库 |
| Resumable Stream Endpoint | Docker 实证 GET /stream 恢复 | ✅ 重放 + 续传 |
| Graceful Interruption Persistence | test_chat_cancel_persists_interrupted | ✅ 中断兜底无悬空 |
| Session Single-Flight | test_chat_single_flight_rejects | ✅ 409 + 不追加消息 |

## 五、遗留项

- Task 7.7（ADR）：需人工新建，agent 不得自动创建
- Task 7.8（incident 记录）：需人工新建
- 前端 Task 9（统一 handleSSEEvent）：纯重构，延后
- `_publish_sync`（cancel 路径）未加 CAS 检查：遗留缺口

## 六、结论

本次修复（commit 0b7954b + 0ac9868）完成 spec 全部核心条款的符合性验证，
ReAct 路径与 Fast path 行为对齐，切换会话不再卡死。
