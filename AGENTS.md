- # AGENTS.md — Finance Analysis Agent

  LangGraph 多 Agent A 股分析系统：FastAPI 后端 + React 18/Vite 前端。 输入股票代码，输出多 Agent 辩论式交易决策报告。

  ## 架构速览

  - 五层流水线：4 分析师并行 → Bull/Bear 辩论 → Trader 决策 → 风控辩论 → 基金经理批准
  - 后端 `src/finance_agent/`（nodes/metrics/data/events/export/harness/prompts）
  - 前端 `frontend/`（React + TS + Tailwind + ECharts）
  - LLM：DeepSeek（LiteLLM 路由）；LLM 链路追踪：Langfuse [http://localhost:3000](http://localhost:3000/)
  - StreamRegistry 为进程内内存结构，后端必须单 uvicorn worker 部署（不可 `--workers N`）
  - 详见 `docs/architecture.md`；ADR 见 `docs/adr/`（人工维护，agent 不得新建）

  ## 常用命令

  - 全栈启动：`docker compose up -d --build`
  - 后端：`uv run uvicorn finance_agent.api:app --host 127.0.0.1 --port 8000 --reload`
  - 前端：`cd frontend && npm run dev`
  - 测试 `uv run pytest` ｜ Lint `uv run ruff check` ｜ 类型 `uv run mypy`
  - 前端测试 `cd frontend && npm test`

  ## 任务路由（所有任务进站先分类）

  - **新功能** → OpenSpec delta 提案（`openspec/changes/`）→ Superpowers 管线 （从 writing-plans 进入）→ 验证 → sync + archive
  - **修 bug · 意图不变** → 复现测试 + superpowers:systematic-debugging，不动 openspec
  - **修 bug · 意图变更 / 行为未定义** → 同新功能流程，delta 先行
  - **重大架构决策** → 人工落 `docs/adr/`；**小改动** → 直接改
  - 详见 `docs/project-workflow.md`项目工作流文档

  ## 契约与红线

  - `openspec/specs/` 是系统行为的唯一真相来源；改动前先查； 只经 delta 编辑、sync 合并，禁止手改主规范库
  - 没有先写失败测试的代码，删除重写
  - archive 前置条件：tasks.md 全勾 + verification 通过 + E2E 门禁通过（交互类变更适用）+ 人工验证报告落 `tests/validation/`
  - 「测试全过」≠「行为正确」；交互行为变更必须有人工验证环节

  ## 测试约束

  - **E2E 禁止 mock 被测系统**：拦截伪造业务接口响应（route.fulfill / MSW）= 红线； LLM、第三方 API 可用 `TESTING=1` stub，但须配 @live 用例（nightly 跑真实服务防漂移）； 故障注入（route.abort()）不算 mock
  - E2E 必须通过前端模拟真实输入；直连 API（requests/httpx）属于集成测试
  - 产物位置（禁止根目录新建目录）：fixtures → `tests/fixtures/` ｜ 脚本 → `tests/scripts/` ｜ 验证报告 → `tests/validation/` ｜ E2E 输出 → `tests/e2e/` ｜ 报告 → `reports/`

  ## 工作约定

  - 排查 bug 必须同时查后端日志和 Langfuse trace（输入输出/耗时/异常）
  - 系统性问题记录到 `docs/incidents/`（编号文档 + 更新 README 索引）
  - 新功能先检查 `src/finance_agent/` 是否已有可复用模块
  - Issue 一律用 `gh` CLI（见 `docs/agents/issue-tracker.md`）； 标签规范见 `docs/agents/triage-labels.md`
