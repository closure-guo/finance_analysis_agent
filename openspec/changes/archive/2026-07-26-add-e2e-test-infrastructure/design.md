## Context

F1（已合并）把 E2E 门禁（Step 4.5）写进了 `docs/project-workflow.md`，但门禁本身没有可执行的基础设施。本变更（F2）补齐最小可执行骨架，让 `npx playwright test` 一条命令能拉起前后端并跑绿 smoke，关闭 F1 留下的「生效过渡语」。

**现状盘点**（影响本设计的关键发现）：

| 项 | 现状 | 对 F2 的影响 |
|---|---|---|
| `/api/health` 端点 | **已存在**（`api.py:462-464`，返回 `{"status":"ok"}`） | F2 无需新增端点，Playwright config 直接用 `/api/health` 轮询 |
| 后端启动与 LLM 的关系 | Agent 在请求时才创建（`agent_factory.py:418-419`），模块级只 `build_5layer_graph()`（不连 LLM） | TESTING=1 下后端能直接启动，不需要完整 LLM stub 也能跑 /api/health |
| LLM 客户端注入点 | `agent_factory._make_llm_client(model, api_key)` 是唯一注入点 | F2 在此声明 TESTING 分支骨架，完整 stub 实现推迟到 F3 |
| 现有 pytest E2E | `tests/e2e/` 下混杂真 LLM 慢链路 + 截图式浏览器脚本 | F2 不迁移，F3 任务 |

## Goals / Non-Goals

**Goals:**

1. `tests/e2e/playwright/` TS Playwright 项目骨架可运行
2. `playwright.config.ts` 双 webServer 配置拉起前后端（后端以 `TESTING=1` 启动）
3. `smoke.spec.ts` 验证前端首页可达 + 后端 `/api/health` 返回 200
4. 后端 `TESTING=1` 开关可读（环境变量 -> 模块级常量），`/api/test/seed` 与 `/api/test/reset` 端点骨架存在（返回 200 占位响应）
5. `agent_factory._make_llm_client` 处有 TESTING 分支注释 + 占位 return（声明注入点，不实现 stub 逻辑）

**Non-Goals:**

1. **不实现完整 LLM stub**（按固定节奏吐 SSE delta）--推迟到 F3，因 smoke.spec 不触发真实分析流程
2. **不迁移存量 pytest E2E**--F3 任务
3. **不写 streaming/contract/interaction spec**--F3 任务
4. **不接 CI**--F4 任务
5. **不接 e2e-skills 工具链**--F4 任务
6. **不实现 `/api/test/seed` 的造数据逻辑**--F2 只做端点骨架（返回 200 + `{"status":"ok"}`），造数据逻辑随 F3 spec 落地

## Decisions

### D1: TS Playwright 项目落 `tests/e2e/playwright/`，不新建根目录 `e2e/`

**选择**：`tests/e2e/playwright/`
**理由**：AGENTS.md 红线「产物位置：E2E 输出 -> `tests/e2e/`，禁止根目录新建目录」。`tests/e2e/` 已存在（pytest E2E），TS 项目作为子目录落入。
**备选**：根目录 `e2e/`（E2E 方案原文）--违反红线，否决。

### D2: 后端启动命令用 `uv run uvicorn finance_agent.api:app`，不新建 `backend/main.py`

**选择**：`cd <repo-root> && TESTING=1 uv run uvicorn finance_agent.api:app --port 8000`
**理由**：AGENTS.md「常用命令」已记录此启动方式；`api.py:41` 的 `app = FastAPI(...)` 是 ASGI 入口。E2E 方案原文的 `cd ../backend && uvicorn main:app` 路径不适用于本项目结构（无 `backend/` 目录，app 在 `finance_agent.api`）。
**备选**：新建 `backend/main.py`--引入冗余文件，违反 YAGNI。

### D3: TESTING=1 开关做最小实现，不实现 LLM stub

**选择**：`api.py` 模块级读 `os.getenv("TESTING")`，存为常量 `TESTING`；`agent_factory._make_llm_client` 处加 `if TESTING: # TODO F3: return stub` 注释占位。
**理由**：后端启动不依赖 LLM 连接（Agent 延迟创建），smoke.spec 只验证 `/api/health` 和前端首页，不需要真实分析流程。完整 stub 推迟到 F3（streaming.spec 才需要确定性流式输出）。
**备选**：F2 实现完整 stub--范围蔓延，违反 YAGNI；smoke.spec 不需要它也能跑绿。

### D4: `/api/test/seed` 与 `/api/test/reset` 做端点骨架，不实现造数据逻辑

**选择**：`TESTING=1` 下注册两个端点，返回 `{"status":"ok","mode":"testing"}`；非 TESTING 下返回 404。
**理由**：F3 的 spec 才会用到造数据（如 `request.post('/api/test/seed', {data: {symbol:'300308'}})`）。F2 只需端点存在且可调用，让 F3 的 spec 任务卡能直接写 `beforeEach` 调用而不需再改后端。
**备选**：F2 不加端点，等 F3 再加--会导致 F3 的 plan 同时改后端 + 写 spec，违反任务单一职责。

### D5: webServer `reuseExistingServer` 在本地开 `true`，CI 开 `false`

**选择**：`reuseExistingServer: !process.env.CI`
**理由**：本地开发时后端可能已在跑（`uv run uvicorn ... --reload`），复用避免端口冲突；CI 必须全新启动确保隔离。与 E2E 方案原文一致。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| TESTING=1 开关只做骨架，F2 验收时后端启动但 LLM 未替换，若 smoke.spec 误触发分析流程会连真 LLM | smoke.spec 只做 `page.goto('/')` + `expect(title)` + `request.get('/api/health')`，明确不触发 `/api/analyze` 或 `/api/chat` |
| `tests/e2e/playwright/` 与现有 `tests/e2e/*.py` 并存，命名混淆 | TS 项目在子目录 `playwright/` 内，与根目录的 `*.py` 物理隔离；README 中注明分工 |
| Windows 下 `cd ../backend && uvicorn main:app` 路径分隔符问题 | 用 `cwd` 参数指定工作目录为 repo-root，不用 `cd` 链；命令为 `uv run uvicorn finance_agent.api:app --port 8000` |
| F2 完成后「生效过渡语」需移除，但 F3 未完成时门禁仍无 spec 可跑 | F2 完成后 smoke.spec 已能跑绿，门禁对 smoke 级别已生效；streaming/contract spec 在 F3 补齐后门禁对交互类变更完全生效。移除过渡语，改为「门禁对已存在的 spec 生效」 |
