# 隐藏工具调用横幅（web search 时）人工验证报告

**日期**: 2026-07-27
**Delta 提案**: hide-tool-use-banner-during-web-search
**验证人**: 实施者 + E2E 自动化验证

## 变更概述

当 Agent 调用 `web_search` / `batch_web_search` 工具时，前端原先会同时显示两个横幅：
- 工具调用横幅（ToolCallBanner）："调用工具中 · N 次" / "已调用工具 · N 次"
- 搜索横幅（SearchBanner）："正在搜索：xxx" / "搜索了 N 个网页"

本变更在前端消费侧过滤搜索类工具，使其不进入 `toolCalls` 数组，仅由独立搜索横幅承载，消除重复展示。

## 验证项

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | `web_search` tool_call 事件不进入 `toolCalls` 数组 | 通过（单测） |
| 2 | `batch_web_search` tool_call 事件不进入 `toolCalls` 数组 | 通过（单测） |
| 3 | `web_search` tool_result 事件不附加结果、不新建记录 | 通过（单测 + 代码审查） |
| 4 | `search_stock` 等非搜索类工具仍正常进入工具调用横幅 | 通过（单测：isSearchTool 返回 false） |
| 5 | 历史会话恢复时过滤搜索类工具，不还原到工具调用横幅 | 通过（代码审查） |
| 6 | `search_result` 中失效的 toolCall `done` 标记分支已清理 | 通过（代码审查） |
| 7 | web search 时只显示搜索横幅、不显示工具调用横幅 | 通过（E2E @live） |

## 单元测试结果

| 测试 | 结果 |
|------|------|
| `SEARCH_TOOL_NAMES` 包含 web_search 与 batch_web_search，size 为 2 | 通过 |
| `isSearchTool` 对 web_search / batch_web_search 返回 true | 通过 |
| `isSearchTool` 对 search_stock / run_deep_analysis / unknown 返回 false | 通过 |

测试文件：`frontend/src/test/toolCallFilter.test.tsx`
运行命令：`cd frontend && npm test`
结果：8/8 全部通过（含既有 smoke / SearchBanner 测试）

## E2E 测试结果（@live，真实 LLM + Tavily）

| 测试 | 结果 | 耗时 |
|------|------|------|
| search-banner.spec.ts › web search 时只显示搜索横幅，不显示工具调用横幅 | 通过 | 17.1s |

测试文件：`tests/e2e/playwright/tests/search-banner.spec.ts`
运行命令：`CI="" npx playwright test search-banner --grep "不显示工具调用横幅" --reporter=line`

断言策略：
- 等待搜索横幅出现（`text=/正在搜索|搜索了/` 可见，90s 超时覆盖真实 LLM 往返）
- 断言工具调用横幅不出现（`text=/调用工具中|已调用工具|工具调用/` 的 `toHaveCount(0)`）
- 覆盖搜索进行中与完成两种状态（断言在搜索横幅可见后立即检查，此时若未过滤会同时出现工具调用横幅）

## 代码改动清单

| 文件 | 改动 |
|------|------|
| [frontend/src/App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) | 1) 顶部导出 `SEARCH_TOOL_NAMES` 常量与 `isSearchTool` 纯函数；2) `handleChatStreamEvent` 的 `tool_call` / `tool_result` case 开头对搜索类工具早返回；3) `selectSession` 还原 `tool_calls` 时过滤搜索类工具；4) 清理 `search_result` 中失效的 toolCall `done` 标记分支；5) 顺手修复 `msg.durationMs` possibly undefined（预先存在，阻塞 build） |
| [frontend/src/test/toolCallFilter.test.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/test/toolCallFilter.test.tsx) | 新增 3 个单元测试（SEARCH_TOOL_NAMES / isSearchTool 行为） |
| [tests/e2e/playwright/tests/search-banner.spec.ts](file:///d:/WorkSpace/finance_analysis_agent/tests/e2e/playwright/tests/search-banner.spec.ts) | 新增 1 个 @live E2E 用例（断言不显示工具调用横幅） |

## 设计决策要点

- **过滤点集中在 `handleChatStreamEvent` 内部**：该函数是深度模式（`startAnalysis`）与快速模式（`quickChat`）共用的事件处理器，一处改动同时覆盖两种模式
- **非搜索类工具行为不变**：`search_stock` 等仍由工具调用横幅展示；当一条消息同时存在搜索横幅与非搜索类 toolCalls 时，两个横幅各司其职并存
- **历史会话同步过滤**：保证实时流与历史会话展示一致

## 备注

- E2E 标记为 `@live`：依赖真实 LLM tool_call + Tavily 搜索；本地运行需 `CI=""`（IDE 默认注入 CI=true 会导致 playwright 不复用现有后端）+ 真实 `DEEPSEEK_API_KEY`
- 顺手修复的 `msg.durationMs` 报错是预先存在的 TS 严格性问题（与本 change 无关），但阻塞了 build 验证，经用户同意一并修复
