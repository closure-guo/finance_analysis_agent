# 人工验证报告: update-file-export-entry

**日期**: 2026-08-25
**验证人**: agent（自动化验证：后端回归 + 前端单测 + E2E 门禁）；主观体验项待人工抽查
**关联 delta**: openspec/changes/update-file-export-entry/
**E2E 门禁**: tests/e2e/playwright/playwright-report（`playwright.timeline.config.ts` 抽查 `report-export` → 1/1 passed，两次运行均绿：40.4s / 42.2s）
**分支**: feat/update-file-export-entry
**实现提交**: 功能/测试提交 be0533a → 55c3c6d（fix）→ ce7eb85（fix），本验证报告为收尾提交

## 变更类型判别

交互类变更（前端 UI + 会话切换/状态流转）：按 `docs/project-workflow.md` §3 完整管线执行，E2E 门禁适用（本 delta 核心 spec `report-export.spec.ts` 已在 timeline 门禁配置内并全绿）。

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 报告卡头部标题「名称（代码）」且无 open-files-banner | 是（report-export.spec.ts:53-58 断言 heading `贵州茅台（600519）` + `open-files-banner` toHaveCount(0)） | 标题为组合格式、旧导出入口消失 | E2E 断言通过；单测 fileExportEntries.test.tsx 同断言 | ✅ |
| 报告名横幅标题与位次（先于全部文件横幅） | 是（report-export.spec.ts:61 断言 `report-name-banner` 可见；spec 注释说明位次语义） | 横幅标题=「名称（代码）」、紧随报告轮次 | E2E 可见性通过；单测 reportEntryBanners.test.tsx（formatReportTitle 名称/缺失/等于代码三态 + 点击回调） | ✅ |
| 全部文件横幅位于对话尾部 | 是（report-export.spec.ts:62 断言 `conversation-files-banner` 可见；74-75 点击等价重开） | 会话尾部单一张，无可导出报告时隐藏 | E2E 通过；单测 reportEntryBanners / fileExportEntries 覆盖条件渲染 | ✅ |
| 顶部栏「查看全部文件」按钮 | 是（report-export.spec.ts:63 可见、66 点击） | 有可导出报告时显示，无/空态隐藏 | E2E 通过；单测 fileExportEntries 覆盖 chat 会话隐藏态 | ✅ |
| 点击任一入口打开抽屉且仅列已生成文件、无三格式行 | 是（report-export.spec.ts:67-69 戳 topbar 入口 → `export-drawer`/`drawer-file-list`/`download-file-*` 第一条可见）；无三格式行由结构保证（`frontend/src/` 已无 `api/export` 调用，抽屉仅遍历 `filePaths` 键） | 抽屉列出 filePaths 条目，无 pdf/docx/markdown 矩阵、无现场生成按钮 | E2E 双入口等价通过（75 行再开）；单测 fileExportEntries 断言 `download-file-md` | ✅ |
| 无可导出文件（快速对话/空态）时三入口不出现 | 否（E2E spec 无该分支；前端单测兜底） | chat 会话/空态下 report-name-banner、conversation-files-banner、topbar-files-button 均不渲染 | fileExportEntries.test.tsx「无可导出文件（快速对话会话）不显示横幅与顶部按钮」通过（topbar 主动 waitFor null） | ✅ |
| 刷新恢复后 file_paths 还原、导出入口仍在 | 否（E2E spec 无刷新分支；前端单测兜底） | GET /api/sessions/{id} 返回 file_paths → streamStore 重建 reportMsg → 三入口再现 | fileExportEntries.test.tsx「恢复已完成报告会话」通过（mock 会话含 file_paths → 三入口可见）；后端 test_session_file_paths.py 两条（落库+旧会话空兼容）通过 | ✅ |
| 下载文件名含「名称_代码」 | 否（E2E 断言下载链接存在，不断言文件名内容；后端单测断言命名） | `{名称}_{代码}_{日期}_report.{ext}`，名称缺失回退仅代码 | tests/export/test_service.py::test_export_report_filename_contains_stock_name + test_export_report_filename_fallback_when_name_equals_code 通过（全量回归绿） | ✅ |
| 抽屉预览/关闭行为保持不变 | 是（report-export.spec.ts:72-73 关闭按钮 → 抽屉消失） | reportMarkdown 预览、X/遮罩/Esc 关闭 | E2E 关闭路径通过 | ✅ |

## 回归证据

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端全量回归 | `uv run pytest -q` | **1263 passed, 2 skipped, 4 failed**，32 warnings。4 失败均为 `@live` 用例（`tests/outcome/test_outcome_live.py`×2 真实 AKShare、`tests/test_trace_content_live.py`×2 需 DEEPSEEK_API_KEY 且 `-m "not live"` 不入 PR 门禁）——环境依赖既有失败，非本 delta 引入 |
| 后端 lint | `uv run ruff check` | tracked 树全绿；仅 `scripts/` 未跟踪目录 `evals_gated_run.py`（4）/`observe_langfuse_experiments.py`（7）共 11 错，属前 delta 工作产物（2026-08-24 报告已记录） |
| 后端类型 | `uv run mypy src/finance_agent` | **69 errors**，与已记录基线一致（2026-08-25-enhance-agent-prompt-quality 报告同 69）；`api.py` 恰 5 错误与 Task 1 基线吻合——本 delta 无新增 |
| 前端全量测试 | `cd frontend && npx vitest run` | **39 files / 344 tests 全过，0 failed** |
| E2E 门禁 | `cd tests/e2e/playwright && npx playwright test --config=playwright.timeline.config.ts report-export` | **1/1 passed**（两次运行 40.4s / 42.2s）；`smoke` 参数在 timeline 配置 testMatch 无匹配（smoke.spec.ts 非该门禁范围，符合设计） |

## 异常记录

- **E2E 首次 MISS：ReAct 路径 report_ready 缺字段**。`report-export` spec 重写（be0533a）后在真实事件通路暴露：ReAct（快速/深度搜索）路径借 agent_factory 发射的 `report_ready` 缺 `stock_code`/`file_paths`，前端据此组合标题与可导出判定时数据缺口 → 已由 **55c3c6d**（`src/finance_agent/agent_factory.py` 补齐两字段 + `tests/test_deep_analysis_tool.py` 新增 29 行断言）修复，本次 E2E 全绿复证。
- **locator 歧义**：报告卡 h3 与报告名横幅标题同为「名称（代码）」，文本定位多匹配 → 已由 **ce7eb85** 将标题断言改为 `getByRole('heading', { name })` 消除歧义，本次运行无歧义。
- **本步运行无新增异常**。附带说明：`playwright.config.ts`（默认门禁）下补跑 `smoke` 时 `/api/test/seed` 失败，根因为 `reuseExistingServer` 复用了 8000 端口上非 TESTING=1 的遗留服务进程（/api/health 200 但 seed 404）——环境残留，非本次变更；本 delta 门禁走 timeline 自管端口对（8001/8002/8003），不受影响。

## 结论

[x] **E2E 覆盖项全部通过**（report-export 1/1、双跑均绿）；后端 1263 用例绿 + ruff tracked 全绿 + mypy 无新增错误；前端 344 用例绿。任务 5.5 中需人工抽查的主观体验项（真实浏览器双横幅观感、真实下载文件名目检）**待人工确认后 archive**——本报告如实区分「E2E 断言覆盖」与「单测兜底」两类证据，未将非 E2E 断言项谎报为 E2E 覆盖。