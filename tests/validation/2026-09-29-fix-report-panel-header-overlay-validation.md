# 人工验证报告: fix-report-panel-header-overlay

**日期**: 2026-09-29
**验证人**: ZCode（自动执行 + 真实浏览器目视抽查）
**关联类型**: 修 bug · 意图不变（A 类，systematic-debugging；不触碰 openspec）
**E2E 门禁**: tests/e2e/playwright/test-results（report-panel-overlay.spec.ts 绿；本报告落盘前失败证据已清理，红→绿证据见下文）

## 用户报告

打开报告右侧面板后：① 面板顶部工具栏（title「完整报告」+ 导出芯片）与主顶栏（查看全部文件 / 设置 / 圆形占位）重叠叠字；② 主顶栏右侧圆形头像框意义不明、无法点击，要求移除。

## 根因（真实 Chromium 复现证实）

1. **重叠根因**：`ReportSidePanel.tsx` 与 `ReportFileDrawer.tsx` 根节点背景使用主题中**不存在的令牌** `var(--bg-base)`（index.css 只定义 `--bg-base-default` / `--bg-base-secondary`）→ 背景声明无效为**透明**。面板 z-55 > 顶栏 z-50，hit-test 归面板（所以顶栏按钮/圆框「无法点击」），但顶栏整行透过透明背景可见，两层文字/芯片互相叠刻（用户截图中圆框里的「M」即 MD 芯片叠在圆形占位上）。
2. **圆形占位**：`App.tsx` 主顶栏渲染了一个纯装饰空 div（`w-7 h-7 rounded-full`），无任何交互与规格出处。

## 变更清单

| 文件 | 变更 |
|---|---|
| `frontend/src/components/ReportSidePanel.tsx` | 背景 `var(--bg-base)` → `var(--bg-base-default)`（附注释锚点） |
| `frontend/src/ReportFileDrawer.tsx` | 同上（同一根因同修） |
| `frontend/src/App.tsx` | 移除主顶栏圆形装饰占位 div |
| `tests/e2e/playwright/tests/report-panel-overlay.spec.ts` | 新增复现 spec（红→绿） |
| `tests/e2e/playwright/playwright.timeline.config.ts` / `playwright.config.ts` | spec 挂载 timeline 套件（pipeline 8002/5175），默认 config 排除 |

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 面板背景不透明 | 是（report-panel-overlay.spec.ts step 6，toHaveCSS） | background-color ≠ transparent | 修复前 `rgba(0,0,0,0)`（红）；修复后非透明（绿） | ✅ |
| 面板操作栏行不被主顶栏覆盖 | 是（step 7，工具栏行逐点 elementFromPoint 采样） | 采样点顶层元素全部属于面板 | 修复前后均通过（z 序本就正确，缺陷在透明背景）；保留作 z 序回归锚点 | ✅ |
| 主顶栏无圆形装饰占位 | 是（step 8，toHaveCount(0)） | 无 `header div.w-7.h-7.rounded-full` | 修复前 count=1（红）；修复后 count=0（绿） | ✅ |
| 导出抽屉（同令牌同修）回归 | 是（report-export.spec.ts 全绿） | 抽屉打开后文件列表可读、双入口等价 | 通过 | ✅ |
| 修复后目视抽查（Playwright headless 截图） | 否（人工目视） | 面板工具栏「完整报告 + DOCX/PPTX/MD + ✕」干净不叠字，顶栏不透出 | 目视符合 | ✅ |
| 前端单测 / 类型 | 否 | vitest 全绿、tsc -b 无错 | 75 文件 620 用例全过；tsc 通过 | ✅ |

## 异常记录

- 诊断过程中发现 IAB（ZCode 内置浏览器）动画时钟节流会冻结 300ms 滑出过渡，transform 读数不可靠（与 memory `iab-frozen-css-transitions` 一致）；最终证据全部取自项目 E2E 栈（headless Chromium），未采信 IAB 帧。
- **附带发现（未在本修处理，建议开 issue）**：`frontend/src/PipelineGraph.tsx:78,182,185` 使用未定义令牌 `var(--text-primary)` / `var(--bg-primary)`（节点卡背景透明回退，当前视觉可接受）；`frontend/src/App.css` 存在 Vite 脚手架遗留的未定义令牌（`--accent-bg` 等，该文件未生效）。可用 `var(--*)` 使用集合与 index.css 定义集合的差集做一次性清查。

## 结论

[x] 全部通过。修复未提交（工作区 App.tsx 另有其他会话未提交改动，为避免混入其 WIP 未执行 git commit）；建议按 `fix: [frontend] 报告面板/抽屉背景令牌不存在致透明——顶栏透出叠字 + 移除顶栏圆形装饰占位` 提交并走 PR。
