## Why

F1（已完成）把 E2E 门禁（Step 4.5）写进了项目工作流，但门禁本身没有可执行的基础设施--`tests/e2e/playwright/` 目录不存在，后端没有 `/health` 端点，`TESTING=1` 开关未实现，LLM stub 未接入。这导致工作流文档中的「生效过渡语」无法被关闭：交互类变更仍只能沿用原人工验证，门禁红线形同虚设。现在补齐基础设施，让 `npx playwright test` 一条命令能拉起前后端并跑绿 smoke，为 F3（核心 spec）与 F4（CI）铺路。

> 上游设计文档：`docs/superpowers/specs/2026-07-26-e2e-workflow-integration-design.md` §5 F2 阶段

## What Changes

- 新增 `tests/e2e/playwright/` TS Playwright 项目：`package.json`、`playwright.config.ts`（双 webServer 拉起前后端）、`tests/smoke.spec.ts`
- 确认后端已有 `/api/health` 端点（api.py:462，返回 `{"status":"ok"}`），Playwright webServer 用它轮询就绪（**无需新增端点**）
- 后端新增 `TESTING=1` 开关：读环境变量，测试模式下标记测试环境（LLM 客户端注入点暴露，但**完整 stub 实现推迟到 F3**，因 smoke.spec 不需要真实分析流程）
- 后端在 `TESTING=1` 下暴露 `/api/test/seed` 与 `/api/test/reset`（仅测试环境可用，造数据/清理；F2 只做端点骨架，造数据逻辑随 F3 spec 落地）
- `.gitignore` 加 `tests/e2e/playwright/node_modules/` 与 `playwright-report/`
- **不改动**现有业务接口行为；**不迁移**存量 pytest E2E（F3 任务）

## Capabilities

### New Capabilities

- `e2e-infrastructure`: E2E 测试基础设施的行为契约--后端测试模式开关、健康检查端点、LLM stub 接口；前端无新行为（仅作为被驱动方）

### Modified Capabilities

无。本变更不修改已有 frontend spec 行为契约；后端 `/health` 与 `TESTING` 开关是新增能力，不触碰现有 `/api/analyze`、`/api/chat` 等接口的契约。

## Impact

| 范围 | 影响 |
|---|---|
| 后端 `src/finance_agent/api.py` | 新增 `TESTING=1` 分支与 `/api/test/seed`、`/api/test/reset` 端点骨架（`/api/health` 已存在，复用） |
| 后端 `src/finance_agent/agent_factory.py` | 新增 TESTING 分支声明 stub 注入点（完整 stub 实现在 F3） |
| 新增 `tests/e2e/playwright/` | TS 项目骨架（package.json / config / smoke spec） |
| `.gitignore` | 加 playwright 产物 |
| 文档 | `docs/project-workflow.md` Step 4.5 的「生效过渡语」可移除（F2 完成即门禁生效） |

依赖：`@playwright/test`（npm）、Node 22+、现有 `uv run uvicorn finance_agent.api:app` 启动方式。无新外部服务。
