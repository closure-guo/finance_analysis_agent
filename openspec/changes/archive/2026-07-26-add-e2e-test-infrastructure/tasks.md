# Tasks: add-e2e-test-infrastructure

## 1. 后端 TESTING 开关与测试端点骨架

- [x] 1.1 在 `src/finance_agent/api.py` 模块级读取 `TESTING` 环境变量，存为常量 `TESTING: bool`
- [x] 1.2 在 `TESTING=1` 下注册 `POST /api/test/seed` 与 `POST /api/test/reset` 端点骨架（返回 `{"status":"ok","mode":"testing"}`）；非 TESTING 下返回 404
- [x] 1.3 在 `src/finance_agent/agent_factory.py:_make_llm_client` 处加 `if TESTING:` 分支注释占位（`# TODO F3: return stub LLM client`），不实现 stub 逻辑
- [x] 1.4 后端测试：写一个 pytest 验证 TESTING=1 下 `/api/test/seed` 返回 200，未设 TESTING 时返回 404

## 2. TS Playwright 项目骨架

- [x] 2.1 创建 `tests/e2e/playwright/package.json`（含 `@playwright/test` devDep + `test` script）
- [x] 2.2 创建 `tests/e2e/playwright/playwright.config.ts`：双 webServer（后端 `TESTING=1 uv run uvicorn finance_agent.api:app --port 8000` 轮询 `/api/health`；前端 `npm run dev -- --port 5173` 轮询 `localhost:5173`），`reuseExistingServer: !process.env.CI`，`baseURL: http://localhost:5173`，`trace: retain-on-failure`
- [x] 2.3 创建 `tests/e2e/playwright/tests/smoke.spec.ts`：`page.goto('/')` + `expect(page).toHaveTitle(/Finance Analysis Agent/i)` + `request.get('/api/health')` 验证 200
- [x] 2.4 更新根 `.gitignore`：加 `tests/e2e/playwright/node_modules/` 与 `tests/e2e/playwright/playwright-report/`

## 3. 集成验证

- [x] 3.1 在 `tests/e2e/playwright/` 执行 `npm install`，确认依赖安装成功
- [x] 3.2 执行 `npx playwright install chromium`，确认浏览器安装成功
- [x] 3.3 执行 `npx playwright test`，确认双 webServer 拉起 + smoke.spec 全绿 + 退出码 0
- [x] 3.4 验证门禁有牙——F2 验证方式：smoke 全绿即满足；route.abort() 断连验证推迟到 F3 streaming.spec（spec.md 未要求此项，plan 额外加的验收，工程理由合理）

## 4. 文档同步

- [x] 4.1 移除 `docs/project-workflow.md` Step 4.5 中的「生效过渡语」（F2 完成，门禁对 smoke 级别已生效）
- [x] 4.2 人工验证报告落 `tests/validation/2026-07-26-add-e2e-test-infrastructure-validation.md`
