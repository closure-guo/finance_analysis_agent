# 验证报告：预搜索事件持久化 agentTimeline 修复

## 问题背景

用户反馈：调用股票查询工具后切换会话，当前轮次的 agent 思考和工具调用内容消失，刷新也无法看到。具体表现为"会话在但横幅消失"--思考横幅还在，但 web_search/batch_web_search 的搜索横幅消失。

## 根因

`api.py` 中 `_run_react_analysis` 的时效性查询预搜索逻辑（第 1234-1269 行），`search_start` 和 `search_result` 事件只调用 `registry.publish`（推送给前端实时 SSE），**没有调用 `collector.feed`**（不进入持久化的 `agentTimeline`）。

```python
# 修复前：search_start 只 publish，没 feed collector
await registry.publish(
    session_id, {"type": "search_start", "query": searchQuery, "timestamp": _now()}
)
# collector.agent_timeline 不会有 search item
```

对比其他事件：
- `thinking_token`、`tool_call`、`tool_result`：都有 `collector.feed` + `registry.publish`
- `search_start`、`search_result`：**只有 `registry.publish`**，漏了 `collector.feed`

导致 `chat_history.agentTimeline` 缺少 search item。前端恢复时用 `deserializeTimeline(h.agentTimeline)` 只能拿到 thinking，搜索横幅消失。

**数据证据**（修复前的会话 0e3db0b2-44f）：
```
chat_history assistant 消息:
  thinking: 959ch ✓
  tool_calls: 2 个（web_search, batch_web_search）✓
  agentTimeline: 1 items（只有 thinking）✗  <- 缺少 search item
```

## 修复方案

在 `search_start` 和 `search_result` 的 `registry.publish` 前补上 `collector.feed`，与其他事件保持一致：

```python
# 修复后：search_start 先 feed collector 再 publish
searchStartEvent = {"type": "search_start", "query": searchQuery, "timestamp": _now()}
collector.feed(searchStartEvent)
await registry.publish(session_id, searchStartEvent)

# search_result 同理
searchResultEvent = {"type": "search_result", ...}
collector.feed(searchResultEvent)
await registry.publish(session_id, searchResultEvent)
```

`apply_chat_event`（timeline_builder.py:221-244）已正确实现 search_start/search_result 的 timeline 构建，只需补上 feed 调用即可。

## 验证证据

### 1. 单元测试

**测试文件**：`tests/test_chat_collector_search_timeline.py`

验证 `collector.feed` 处理 search_start + search_result 后 `agent_timeline` 包含 search item。

```
uv run pytest tests/test_chat_collector_search_timeline.py
2 passed
```

### 2. 回归测试

```
uv run pytest tests/test_chat_collector_search_timeline.py tests/test_react_loop.py tests/test_react_background.py
10 passed
```

### 3. Docker 重建 + 集成验证

**环境**：`docker compose up -d --build backend`

**验证脚本**：`tests/scripts/verify_search_timeline_persisted.py`

触发时效性查询"分析热门股票"（触发预搜索），等待 agent 完成，检查 `chat_history.agentTimeline`。

**修复前**（会话 0e3db0b2-44f）：
```
agentTimeline: 1 items
  [0] thinking: 959ch
（缺少 search item）
```

**修复后**（会话 07cad59b-129）：
```
agentTimeline: 6 items
  [0] thinking: 25ch
  [1] search: status=done, results=5    <- 预搜索 web_search
  [2] thinking: 1692ch
  [3] search: status=done, results=5    <- agent web_search
  [4] search: status=done, results=5    <- agent batch_web_search
  [5] thinking: 1805ch

>>> PASS: agentTimeline 包含 3 个 search item
```

修复后 agentTimeline 包含 3 个 search item（每个有 results），前端恢复时能正确渲染搜索横幅。

## 影响范围

- **修改文件**：`src/finance_agent/api.py`（`_run_react_analysis` 预搜索逻辑，补 2 处 `collector.feed`）
- **新增测试**：`tests/test_chat_collector_search_timeline.py`
- **新增验证脚本**：`tests/scripts/verify_search_timeline_persisted.py`
- **无前端改动**
- **无 OpenSpec delta**（属于"修 bug · 意图不变"类型，复现测试 + 根因修复，不动 openspec）

## 验证日期

2026-08-02
