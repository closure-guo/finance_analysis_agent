# 人工验证报告：修复终态事件 CAS 作用域（游标卡死）

- **Change**: `fix-terminal-event-dedup-scope`
- **验证日期**: 2026-08-03
- **验证人**: 项目维护者（人工实操）
- **验证方式**: 全栈启动，浏览器真实交互

## 缺陷背景

终态事件（done/interrupted/error）的 CAS 去重作用域错误地覆盖整个会话 journal 历史。第一轮结束后 journal 中已存在 `done`，第二轮起所有终态事件被 `has_terminal_event` 判定为"已有终态"而丢弃（返回 0，不入 journal、不 fan-out）。前端永远收不到第二轮的终态事件，导致流式游标（streaming-cursor 转圈图标）永久卡死。

触发路径：深度追问且 Agent 再次调用 `run_deep_analysis`（无 `awaiting_input` 兜底、`startAnalysis` 循环无 `chat_done` 分支、`done` 被 CAS 吞掉）。

## 修复内容

| 层 | 改动 | 文件 |
|----|------|------|
| 后端（治本） | 终态 CAS 从"查 journal 全历史"改为 per-run 内存标志 `SessionStream.terminalPublished`；CAS 收敛到 `_try_mark_terminal()`，`publish()` 与 `_publish_sync()` 共用 | `src/finance_agent/stream_registry.py` |
| 前端（纵深防御） | `startAnalysis` SSE 循环补 `chat_done` 分支，路由到 `handleChatStreamEvent` | `frontend/src/App.tsx` |
| 前端（纵深防御） | reader-done 与 catch 块兜底将助手消息 `streaming` 置 false（AbortError 路径除外） | `frontend/src/App.tsx` |

## 验证结论

**游标问题已修复。** 经人工实操确认，第二轮及后续轮次的流式游标能正常消失，不再永久挂在消息末尾。

## 自动化测试结果

| 范围 | 结果 |
|------|------|
| 后端相关测试（terminal_cas / stream_registry / react_resumable / followup_sse_termination / subscribe_order / fastpath_bridge / session_store_terminal） | 37 passed |
| 前端全量 Vitest | 17 files / 147 tests passed |
| `ruff check` | All checks passed |
| `mypy` | Success: no issues found |

新增测试覆盖：

- 后端 `tests/test_terminal_cas.py`
  - `test_per_run_cas_allows_terminal_in_second_round`（参数化 done/interrupted/error）：第二轮终态事件不被吞，journal 含两轮终态
  - `test_per_run_cas_rejects_duplicate_done_within_same_run`：同轮内重复 done 被去重
- 前端 `frontend/src/test/streamingCursorLifecycle.test.ts`（8 个用例）
  - `chat_done` 抵达时游标消失且 thinking item 收口
  - 缺少 `done` 终态事件时流结束仍清除游标（复现原 bug 场景）
  - 终态事件与防御性清理幂等、空流、AbortError 不清游标

## 附带修正：一个假绿测试

`tests/test_react_resumable.py::test_chat_single_flight_rejects_second_request` 原本的通过是**偶然**的，非本次改动引入的回归。

原测试用"读首事件即断开"发起首个请求，但首个 SSE 事件要等 stub `_stub_web_search` sleep 5s 后才到达 —— 此时首个任务已跑完。旧代码中 `publish()` 里那次 `await asyncio.to_thread(has_terminal_event, ...)` 的 DB 扫描恰好推迟了任务注销几毫秒，使 409 断言侥幸落在窗口内。

实测时序对比：

| 版本 | 首事件耗时 | 断言那刻 `is_active` | 结果 |
|------|-----------|-------------------|------|
| 改动前 | 5.633s | `True` | 侥幸 PASS |
| 改动后 | 5.668s | `False` | FAIL |

修正方式：改为后台 task 持续消费首个请求 + `asyncio.sleep(1.0)` 在 stub 5s 窗口内断言 409，与同文件 `test_chat_cancel_persists_interrupted` 的既有模式一致。现在该测试验证的是真正的 single-flight 语义，不依赖调度巧合。

**期间曾错误地保留那句纯为副作用存在的 DB 扫描来"让测试变绿"，识别为坏味道后已推翻重做。**

## 已知 pre-existing 失败（非本次改动引入）

### 1. E2E 五层管线：Fund Manager 决策枚举解析

`tests/e2e/test_5layer_pipeline.py::Test5LayerPipelineE2E::test_full_pipeline_produces_report`

```
AssertionError: assert 'return' in ('approve', 'reject', 'revise')
```

Fund Manager 输出了 `return` 而非预期三个枚举值之一，属决策解析问题，与流式终态事件无关。

已用 `git stash` 隔离验证：**改动前以完全相同的断言失败**（`tests/e2e/test_5layer_pipeline.py:63`），确认为 pre-existing。

已开 issue 跟踪：#34

### 2. asyncio_mode=auto 与 tests/e2e 的 Playwright sync API 冲突

全量 `uv run pytest`（含 `tests/e2e/`）时出现：

```
RuntimeError: Runner.run() cannot be called from a running event loop
RuntimeError: asyncio.run() cannot be called from a running event loop
```

实测定位：

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/ --ignore=tests/e2e --ignore=tests/scripts` | **569 passed**，零 RuntimeError |
| `uv run pytest`（含 e2e） | 出现上述 RuntimeError |

根因为 `asyncio_mode = "auto"` 与 `tests/e2e/conftest.py` 的 Playwright **同步** API（`sync_playwright()`）冲突：sync Playwright 内部调用 `asyncio.run()`，在 pytest-asyncio 已建立的运行中事件循环内被调用即报错。属测试基础设施配置问题，非产品代码缺陷。

已开 issue 跟踪：#35

**归因更正说明**：本报告初版曾将此描述为「约 87 个失败、并跑时事件循环隔离问题」。该数字与归因均不准确 —— 后续实测确认排除 `tests/e2e` 后 569 个测试全部通过，且 `tests/e2e` 仅收集到 6 个测试，凑不出 87 个失败。以上表实测结论为准。

## 改动范围

```
 frontend/src/App.tsx                 | 24 ++++++++++
 src/finance_agent/stream_registry.py | 33 +++++++++++---
 tests/test_react_resumable.py        | 20 +++++++--
 tests/test_terminal_cas.py           | 87 +++++++++++++++++++++++++++++++++++-
```

外加新增 `frontend/src/test/streamingCursorLifecycle.test.ts`。

注：`src/finance_agent/session_store.py` 最终未改动 —— `has_terminal_event` 予以保留（不再被 `publish` 调用，但保留其单测），仅将 CAS 决策迁至内存标志。

