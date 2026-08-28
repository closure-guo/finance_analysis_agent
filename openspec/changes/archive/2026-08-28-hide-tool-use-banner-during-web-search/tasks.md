## 1. 提取搜索类工具名常量与纯函数

- [x] 1.1 在 `frontend/src/App.tsx` 顶部定义并导出 `SEARCH_TOOL_NAMES` 常量（`Set<string>`，含 `'web_search'`、`'batch_web_search'`）与纯函数 `isSearchTool(name: string): boolean`（判断 name 是否属于 `SEARCH_TOOL_NAMES`），供实时流过滤与历史会话恢复复用

## 2. 编写失败测试（TDD 红线）

- [x] 2.1 在 `frontend/src/test/` 新增 `toolCallFilter.test.tsx`：断言 `isSearchTool('web_search')` 与 `isSearchTool('batch_web_search')` 返回 `true`，`isSearchTool('search_stock')`、`isSearchTool('run_deep_analysis')`、`isSearchTool('unknown')` 返回 `false`
- [x] 2.2 同测试文件：断言 `SEARCH_TOOL_NAMES` 包含 `'web_search'` 与 `'batch_web_search'`，且 size 为 2
- [x] 2.3 运行 `cd frontend && npm test`，确认 2.1-2.2 当前失败（`isSearchTool` / `SEARCH_TOOL_NAMES` 尚未导出，导入会报错）

## 3. 实时流过滤实现

- [x] 3.1 在 `handleChatStreamEvent` 的 `tool_call` case（`App.tsx` 第 741-750 行）开头，若 `SEARCH_TOOL_NAMES` 包含 `event.name`，直接 `return true` 跳过 `toolCalls` 追加
- [x] 3.2 在 `handleChatStreamEvent` 的 `tool_result` case（`App.tsx` 第 752-777 行）开头，若 `SEARCH_TOOL_NAMES` 包含 `event.name`，直接 `return true` 跳过附加结果与新建记录

## 4. 历史会话恢复过滤

- [x] 4.1 修改 `selectSession` 还原 `tool_calls` 逻辑（`App.tsx` 第 185-187 行），过滤 `name` 属于 `SEARCH_TOOL_NAMES` 的条目，仅当过滤后列表非空时设置 `toolCalls`

## 5. 清理失效逻辑

- [x] 5.1 清理 `search_result` 事件中标记 `web_search` / `batch_web_search` toolCall `done: true` 的逻辑（`App.tsx` 第 459-464 行），因搜索类工具不再进入 `toolCalls`，该标记分支已失效

## 6. 验证

- [x] 6.1 运行前端单元测试：`cd frontend && npm test`，确认 2.1-2.2 全部通过
- [x] 6.2 运行前端类型检查与构建：`cd frontend && npm run build`
- [x] 6.3 E2E（落 `tests/e2e/`）：启动前后端真实服务，快速模式触发 `web search`，通过前端模拟用户真实输入，断言只显示搜索横幅、不显示工具调用横幅
- [x] 6.4 人工验证报告落 `tests/validation/`
