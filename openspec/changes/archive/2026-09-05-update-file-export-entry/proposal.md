# Proposal: update-file-export-entry

## Why

当前「全部文件」导出入口固定在报告卡标题区（分析管线 UI 的标题位置），报告较长或页面滚动后该入口不可见，且入口与「会话」「报告轮次」的绑定关系不直观。期望将导出入口调整为会话级双横幅 + 全局顶部栏按钮：对话尾部「全部文件」横幅、报告产出轮次底部的「报告名」横幅，以及始终可及的顶部栏按钮，均打开右侧文件列表抽屉。

## What Changes

- 移除报告卡标题区的「全部文件」按钮（`open-files-banner`），报告头部不再承载任何文件导出入口
- 对话区内新增双横幅：
  - 「报告名横幅」：以「股票名称（股票代码）」为标题（如「贵州茅台（600519）」），位于产出该报告的对话轮次底部（紧随报告消息及其后的「分析完成」系统消息）、位次先于「全部文件」横幅；仅在产出报告的轮次出现
  - 「全部文件横幅」：位于对话尾部（最后一条消息之后），会话存在可导出报告时显示
  - 点击任一横幅均打开右侧文件列表抽屉
- 报告数据链路补齐股票名称与代码：后端 `report_ready` 事件增发 `stock_code`，前端报告消息记录 `stockCode` 字段；报告卡头部标题与报告名横幅均以「股票名称（股票代码）」组合展示（名称与代码一致或缺失时回退仅显示代码，历史会话恢复时用会话元数据兜底）
- 会话持久化报告文件产物：会话表新增 `file_paths` 列并在报告完成时写库，`GET /api/sessions/{id}` 返回该字段，前端恢复会话时还原 `filePaths`（否则刷新后按「已生成文件」口径判定的导出入口全部消失）
- 可导出报告判定口径：完成的报告消息且其 `filePaths` 含至少一个已生成文件（仅「有已生成报告 markdown」不算可导出）
- 导出报告文件名加入股票名称：自动生成的文件名由「{代码}_{时间戳}_report」改为「{股票名称}_{代码}_{时间戳}_report」格式（名称缺失时回退仅代码）
- 全局顶部栏（固定导航栏，设置按钮旁）新增「查看全部文件」按钮，会话存在可导出报告时显示，点击打开同一抽屉
- 右侧文件列表抽屉改为：自上而下仅列出该会话报告已生成的可下载文件（`filePaths` 各条目，按扩展名区分图标），移除 pdf/docx/markdown 三类固定格式行与缺失格式的现场生成按钮；预览与关闭行为不变

非 **BREAKING**：仅前端入口位置、可见性与抽屉列表形态变化，`/api/files`、`/api/export` 契约与后端行为不变。

## Capabilities

### New Capabilities

无（本变更不引入新能力，全部行为落在既有 `frontend` 能力内）。

### Modified Capabilities

- `frontend`: 「Report Card Rendering」移除报告头部文件导出按钮；新增 ADDED 需求「会话级文件导出入口」，定义报告名横幅、全部文件横幅与全局顶部栏按钮的显示条件、位次关系，以及抽屉仅列出已生成可下载文件的行为。

## Impact

- 前端（主要）：`frontend/src/App.tsx`（ReportCard 移除导出按钮、头部标题「名称（代码）」、对话区内渲染报告名横幅与全部文件横幅、顶部栏按钮、消息列表末尾条件渲染）、`frontend/src/ReportFileDrawer.tsx`（文件列表由遍历格式矩阵改为遍历 `filePaths`）、`frontend/src/types.ts` 与 `frontend/src/stores/streamStore/reduce.ts`（UIMessage 增加 `stockCode` 字段并在 report_ready 处理时落库）、相关单测（`frontend/src/test/reportFileDrawer.test.tsx` 及新增横幅/按钮用例）
- 后端（小）：`src/finance_agent/api.py` 的 `report_ready` 事件载荷增发 `stock_code` 字段（仅新增字段，非破坏性契约扩充）；`src/finance_agent/export/service.py` 自动生成报告文件名加入股票名称；`src/finance_agent/session_store.py` 会话表新增 `file_paths` 列并在报告完成时持久化、`GET /api/sessions/{id}` 返回该字段（非破坏性向后兼容迁移）
- 前端 E2E：`e2e/tests/`（交互类变更，需新增/更新 spec 覆盖双横幅与顶部按钮）；`report_ready` 载荷变化需同步 e2e LLM stub 与 fixtures、后端 SSE 事件契约测试
- 依赖项：本变更复用 `add-report-export` 已实现的抽屉能力（代码在位，其 delta 尚未 sync 主库；实施前需确认该能力可用，见 design.md）