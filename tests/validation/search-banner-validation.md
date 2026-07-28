# 搜索横幅人工验证报告

**日期**: 2026-07-27
**Delta 提案**: add-search-banner
**验证人**: 实施者 + E2E 自动化验证

## 验证项

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | 快速模式：搜索中显示"正在搜索：{query}"脉冲动画 | 通过 |
| 2 | 快速模式：搜索完成显示"搜索了 N 个网页" | 通过 |
| 3 | 快速模式：点击展开查看网页列表（标题+摘要+域名+favicon） | 通过 |
| 4 | 快速模式：搜索失败显示错误状态 | 通过（代码审查） |
| 5 | 深度模式：澄清阶段搜索以独立搜索横幅展示（非 ToolCallBanner 摘要） | 通过（代码审查） |
| 6 | 搜索横幅与思考横幅/工具调用横幅视觉协调，不重叠 | 通过（代码审查） |

## E2E 测试结果（@live，真实 LLM + Tavily）

| 测试 | 结果 | 耗时 |
|------|------|------|
| search-banner.spec.ts › 搜索中显示"正在搜索"横幅 | 通过 | 16.0s |
| search-banner.spec.ts › 搜索完成显示"搜索了 N 个网页"并可展开 | 通过 | 18.1s |

测试文件：`tests/e2e/playwright/tests/search-banner.spec.ts`
运行命令：`CI="" LLM_API_KEY=*** npx playwright test search-banner --reporter=list`

## 视觉协调性说明（验证项 6）

三个横幅组件（[SearchBanner](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/SearchBanner.tsx)、[ThinkingBanner](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx#L1437)、[ToolCallBanner](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx#L1498)）共享同一视觉系统：

- 容器样式：`mb-3` + `px-3 py-2 rounded-lg` + `background: var(--bg-overlay-l1)`
- 展开动画：`overflow-hidden transition-all duration-300 ease-out` + `maxHeight/opacity` 切换
- 折叠按钮：`w-full flex items-center gap-2 ... text-left` + hover 态切 `var(--bg-overlay-l2)`
- 图标统一：`fas` 图标系 + `text-xs flex-shrink-0`
- 顺序布局：SearchBanner -> ToolCallBanner -> ThinkingBanner（[App.tsx:1383-1395](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx#L1383-1395)），每个有 `mb-3` 间距，垂直堆叠不重叠

## 验证项 4/5 说明（代码审查）

- **搜索失败状态**（验证项 4）：[SearchBanner.tsx:58-67](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/SearchBanner.tsx#L58-67) 渲染 `fa-exclamation-circle` + "搜索失败"文本，样式与 searching/done 一致
- **深度模式澄清阶段**（验证项 5）：[App.tsx:878-904](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx#L878-904) 快速模式搜索事件处理；深度模式 search_result 已改为设置 `searchStatus/searchResults`（proposal.md 所述），不再附加到 ToolCallBanner

## 备注

- E2E 标记为 `@live`：依赖真实 LLM tool_call + Tavily 搜索，StubLLMClient（TESTING=1）不吐 tool_call 无法触发搜索事件
- 本地运行需 `CI=""`（IDE 默认注入 CI=true 会导致 playwright 不复用现有后端）+ 真实 LLM_API_KEY
- "搜索完成"用例的查询用"茅台最新消息"（时效性问题确保 LLM 触发搜索）；"宁德时代怎么样"LLM 会直接回答不搜索
