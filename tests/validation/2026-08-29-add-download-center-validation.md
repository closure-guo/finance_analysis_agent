# add-download-center 人工验证报告

> 状态：**待人工验证**（自动验证已完成，签字栏留空待用户确认）

## 概述

OpenSpec change `add-download-center`：新增下载管理页（`/downloads`，列表/搜索/类型筛选/下载/删除三态/动效降级）、侧边栏「下载管理」入口、轻量 pathname 路由（pushState + popstate，nginx try_files 已配 SPA fallback）；后端新增 `GET /api/files`、`DELETE /api/files/<name>` 并对三类文件接口统一路径安全校验。

**提交列表**（分支 `feat/design-system-download-center`）：

| 提交 | 内容 |
|---|---|
| 988d447 | feat(api): 文件列表/删除接口 + 三类文件接口统一路径安全（add-download-center 1.1-1.3） |
| d174636 | feat(frontend): /downloads 下载管理页 + 侧边栏入口（add-download-center 2.1-2.6, 3.1-3.3） |
| （本次验证新增）| fix(api): api.py REPORTS_DIR 尊重环境变量（见下方「验证期间发现的修复」） |
| （本次验证新增）| test(e2e): downloads 页面门禁 spec + 本验证报告 |

### 验证期间发现的修复（超出 Task 5 原始清单，TDD 补测）

**api.py `REPORTS_DIR` 此前硬编码 `Path("reports")`，不读环境变量**，而：
- `export/service.py` 写盘侧一直尊重 `REPORTS_DIR` 环境变量；
- E2E 基建（commit 3c544e4「REPORTS_DIR 隔离」+ playwright.config.ts webServer env）一直假定后端尊重该变量。

后果：E2E 环境（`REPORTS_DIR=tmp/e2e-reports-8000`）下 `/api/files` 实际扫描生产 `reports/`（本机 1083 个文件），「stub 环境天然空态」前提不成立；且流水线写盘目录与文件下载/删除接口解析目录不一致。修复为一行（TDD：先在 `tests/test_api_files.py::test_reports_dir_honors_env_override` 红 → 改 `src/finance_agent/api.py` → 绿）：

```python
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
```

## 自动验证结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端测试（全量） | `uv run pytest` | ✅ 1462 passed / 2 skipped / 4 failed——4 个失败均为 `@live` 真实 LLM/行情用例（test_outcome_live 2 例、test_trace_content_live 2 例），本机无真实 API key 的既有环境性失败，与本变更无关 |
| 后端文件接口测试 | `uv run pytest tests/test_api_files.py` | ✅ 7 passed（原 6 例 + 新增 env 覆盖 1 例） |
| Lint / 类型 | `uv run ruff check` / `uv run mypy src` | ✅ ruff 全过；mypy 69 errors 与基线（stash 后）完全一致，全部 pre-existing，本变更零新增 |
| 前端测试 | `cd frontend && npm test` | ✅ 42 files / 356 tests 全绿（含 downloads 组件测试 10 例，既有测试零修改） |
| 构建 | `cd frontend && npm run build` | ✅ tsc + vite 通过（4.46s；>500kB chunk 警告为既有） |
| E2E 门禁（本 spec） | `cd tests/e2e/playwright && npx playwright test downloads.spec.ts` | ✅ 隔离运行 3 passed（多次复跑稳定，2-3s/例） |
| E2E 全量对照 | `npx playwright test` | ⚠️ 见下方归因 |

### downloads.spec.ts 覆盖内容（stub 后端，无 LLM 依赖，未 mock 任何业务接口）

1. 侧边栏点击「下载管理」（`sidebar-downloads`）→ URL 变为 `/downloads` 且渲染下载管理页（`download-center`）。
2. 直达 `page.goto('/downloads')`（baseURL 5173）→ 下载管理页渲染；`reload` 后仍停留（刷新保持路由语义）。
3. 空态（`REPORTS_DIR` 隔离目录不存在 → `GET /api/files` 返回 `[]`）→ 显示 `downloads-empty` 与「返回聊天」，点击回跳会话页（EmptyState 标题「Finance Analysis Agent」）。

按 Task 5 约定，E2E 不做文件预埋、不测删除流（删除回滚/筛选等副作用路径由 `frontend/src/test/downloads/` 组件测试覆盖）。

### E2E 全量对照归因（重要）

本机（Windows，默认 config 8 worker）全量运行 4 次，失败集合在 18-20 之间波动，**全部为已知 pre-existing 环境性类别**（与 2026-08-29-refactor-ui-design-system 验证报告归因的 17 failed / 基线 cc00bc0 18 failed 同族）：streaming / concurrent-streaming / debug-switch 系列、search-banner @live、thinking-banner @live、smoke 健康检查、explore、interaction、contract——单次运行间成员有增减（如 smoke、contract、debug-switch-during-thinking 时挂时不挂），纯并发抖动，非本分支引入。

**downloads.spec 在全量下的表现**：入口跳转、直达刷新两例稳定通过；空态例在全量并发下呈现 flaky（重试后通过，不计入 failed）。实测证据（全量运行期间每 3s 采样）：29 个采样点中 27 个 `localhost:8000/api/health` 与 `localhost:5173`（vite 代理）**同时**超时——即全量并发下前后端整机无响应窗口，任何页面级断言都可能被压住；这与 smoke /api/health 的既有失败同根因。空态例为此配置了 `test.describe.configure({ retries: 2 })` + 单测内轮询重载（预算 4 分钟）作环境性兜底；语义验证以隔离运行（3/3 稳定）为准。

**结论：失败集合无本分支新增条目；downloads.spec 自身隔离全绿。**

## 遗留人工检查项（需真实浏览器 + 真实文件，自动验证无法覆盖）

操作步骤建议（docker compose 全栈或 `uv run uvicorn` + `npm run dev`，并在 `reports/` 预置含**中文名**的 .docx/.pptx/.pdf/.md 文件，另建一个非法扩展名文件确认不出现在列表）：

1. **中文文件名下载**：进入 `/downloads`，确认中文文件名完整显示、点击下载落盘文件可正常打开（`Content-Disposition` 编码 / 浏览器接管行为）。
2. **删除回滚**：点击删除 → 确认弹窗 → 删除成功 toast；再断开后端（或改坏一个文件制造 404）后删除 → 确认条目**回滚到原位**（乐观移除失败回滚路径，组件测试已覆盖逻辑，需真实网络环境复核）。
3. **动效降级**：系统开启「减少动态效果」（Windows 设置 > 辅助功能 > 视觉效果 > 关闭动画）后刷新 `/downloads`，确认列表直接呈现、无 framer-motion 入场动画卡顿或残留透明。
4. **空态与直达**：清空 `reports/` 后直达 `/downloads` 与刷新，确认空态与「返回聊天」回跳（E2E 已覆盖，建议真实浏览器复核一次）；nginx 部署形态下直达 `/downloads` 依赖 try_files SPA fallback，建议 `docker compose` 起栈后复核。
5. **列表三态**：停掉后端访问 `/downloads` → 应显示错误态（`downloads-error`）+ 重试按钮，而非以空态冒充。

## 人工验证签字

- [ ] 抽查通过，确认上述遗留项无问题
- 签字/日期：____________
