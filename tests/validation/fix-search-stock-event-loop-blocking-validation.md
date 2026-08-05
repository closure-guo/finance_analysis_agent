# 验证报告：search_stock 事件循环阻塞修复

## 问题背景

用户反馈：进入"识别股票"工具调用节点时切换会话会导致卡顿，并且进入股票分析管线后切换会话会导致无法切回原会话，刷新页面后历史会话清空。

## 根因

`agent_factory.py` 中 `search_stock` async 工具直接调用同步的 `search_stock_tool`（内部含 AKShare 同步重试 3 次，每次可能阻塞 10+ 秒），未用 `asyncio.to_thread` 包装。

```python
# 修复前：同步调用阻塞事件循环
async def search_stock(query: str = "") -> str:
    ...
    result = search_stock_tool(query, api_key)  # 阻塞事件循环
    return _format_stock_result(result)
```

当 LLM 调用 `search_stock` 工具时，AKShare 的同步重试会阻塞 FastAPI 事件循环。期间所有 API 请求（包括 `/api/sessions`）被挂起，表现为：

- 切换会话卡顿：`/api/sessions/{id}` 请求被阻塞，UI 无响应
- 无法切回原会话：同上
- 刷新后历史会话清空：`/api/sessions` 请求超时，前端 `sessions` state 为空（实际数据库 623 个会话完好，数据未丢失）

## 修复方案

用 `asyncio.to_thread` 包装同步调用，让 AKShare 阻塞操作在线程池执行，不阻塞事件循环：

```python
# 修复后：to_thread 包装，事件循环保持响应
async def search_stock(query: str = "") -> str:
    ...
    result = await asyncio.to_thread(search_stock_tool, query, api_key)
    return _format_stock_result(result)
```

与同文件中 `_web_search`、`_batch_web_search` 的处理方式保持一致（均用 `to_thread` 包装同步调用）。

## 验证证据

### 1. 专项测试（TDD 红绿）

**测试文件**：`tests/test_search_stock_event_loop.py`

模拟 `search_stock_tool` 同步阻塞 1 秒，验证 `search_stock` 执行期间事件循环是否保持响应（通过并发 `periodic_wakeup` 任务计数）。

- **修复前**：1.2 秒窗口内仅唤醒 3 次（事件循环被阻塞 1 秒，只剩 0.2 秒收尾时间）-- 成功复现 bug
- **修复后**：1.2 秒窗口内唤醒 20+ 次（事件循环未阻塞）-- 测试通过

### 2. 回归测试

```
uv run pytest tests/test_search_stock_tool.py tests/test_react_loop.py \
  tests/test_react_background.py tests/test_react_resumable.py \
  tests/test_react_pipeline_snapshot.py
33 passed
```

含 13 个 search_stock_tool 测试 + 20 个 ReAct 流程测试，全部通过，无副作用。

### 3. Docker 重建 + 集成验证

**环境**：`docker compose up -d --build backend` 重建后端容器

**验证脚本**：`tests/scripts/verify_search_stock_event_loop.py`

模拟真实场景：
1. 启动 `POST /api/analyze`（输入"安孚科技"，触发 search_stock）
2. 等待进入工具调用阶段
3. 并发请求 `GET /api/sessions`，测量响应时间

**结果**：
```
[1] 启动分析请求（输入: 安孚科技）
[2] 等待工具调用阶段（thinking/tool_call）...
[3] 并发请求 /api/sessions（此时 search_stock 应在执行中）...
[3] /api/sessions 成功：624 个会话（耗时 0.13s）

结论：PASS - 事件循环未阻塞，/api/sessions 在 3 秒内响应
```

修复前同样场景 `/api/sessions` 会超时（10+ 秒无响应，HTTP 000）。

### 4. 数据完整性确认

直接查询数据库确认数据未丢失：
- `data/sessions.db` 中有 623 个会话（修复前后均如此）
- "刷新后历史会话清空"是前端加载请求超时的假象，非真实数据丢失

## 影响范围

- **修改文件**：`src/finance_agent/agent_factory.py`（search_stock 函数，1 处改动）
- **新增测试**：`tests/test_search_stock_event_loop.py`
- **新增验证脚本**：`tests/scripts/verify_search_stock_event_loop.py`
- **无前端改动**
- **无 OpenSpec delta**（属于"修 bug · 意图不变"类型，复现测试 + 根因修复，不动 openspec）

## 验证日期

2026-08-02
