# AI 开发助手说明书

## 项目概述

本项目是 Finance Analysis Agent，基于 LangGraph 多 Agent 架构的 A 股上市公司 AI 分析报告系统。后端使用 FastAPI 框架，前端使用 React 18 + Vite。输入股票代码，自动生成多 Agent 交易决策分析报告。

## 架构说明

- 五层架构：4 分析师并行 -> Bull/Bear 辩论 -> Trader 决策 -> Risk Management 辩论 -> Fund Manager 批准
- 分层职责：
  - L1 前端：React 18 + Vite（表单输入 + 报告展示 + 文件下载）
  - L2 Agent：LangGraph（5 层架构 + 多 Agent 辩论 + Send 并行派发）
  - L3 数据：pandas + SQLite（AKShare 拉取 + 指标计算 + 报表持久化 + 行情缓存）
  - L4 LLM：DeepSeek（LiteLLM 路由）
- 可观测性：Langfuse 追踪 LLM 调用链路（http://localhost:3000）
- 详细架构文档：参见 `docs/architecture.md`
- 架构决策记录：参见 `docs/adr/`

## 目录结构

- `src/finance_agent/` - 后端业务逻辑
  - `nodes/` - LangGraph 节点（分析师、辩论、交易员、风控等）
  - `metrics/` - 财务指标计算（盈利/偿债/现金流/杜邦/GARP/技术面等）
  - `data/` - 数据获取与缓存（AKShare 客户端）
  - `events/` - 事件/新闻流水线
  - `export/` - 报告导出（docx/pptx）
  - `harness/` - Agent 执行框架（LLM 客户端、工具管理、权限）
  - `prompts/` - LLM 提示词模板
- `frontend/` - React 前端（Vite + TypeScript + TailwindCSS + ECharts）
- `tests/` - 测试
  - `fixtures/` - 被测数据快照
  - `scripts/` - 手动验证脚本
  - `validation/` - 人工验证报告
  - `e2e/` - E2E 测试（截图、HTML 输出，gitignored）
- `docs/` - 文档（ADR、架构、设计文档、incidents）
- `data/` - 运行时数据文件（热门股票、关键事件）
- `reports/` - 运行时报告输出（docx/pptx，gitignored）

## 开发规范

- 代码规范：参见`.trae\rules\project_rules.md`
- 测试规范：参见 `pyproject.toml` 中 `[tool.pytest.ini_options]`
- E2E 测试约束：
  - **禁止使用 mock 数据**，必须使用真实服务、真实依赖、真实输入数据（可来自 `tests/fixtures/`）
  - **必须通过前端模拟用户真实输入**，禁止单独测试后端 API；直接用 `requests`/`httpx` 调用接口属于集成测试
- 测试产物存放位置（禁止在根目录创建新目录）：

  | 类型 | 路径 | 说明 |
  |------|------|------|
  | 测试 fixtures | `tests/fixtures/` | 被测数据快照 |
  | 验证脚本 | `tests/scripts/` | 手动验证脚本 |
  | 验证文档 | `tests/validation/` | 人工验证报告 |
  | 运行时报告输出 | `reports/` | docx/pptx 等生成文件（gitignored） |
  | E2E 截图/输出 | `tests/e2e/` | 截图、HTML、report_*.md（gitignored） |

## 常用命令

- 启动项目（全部服务）：`docker compose up -d --build`
- 后端开发：`uv run uvicorn finance_agent.api:app --host 127.0.0.1 --port 8000 --reload`
- 前端开发：`cd frontend && npm run dev`
- 安装依赖：`uv sync`（后端）/ `npm install`（前端）
- 测试：`uv run pytest`
- Lint：`uv run ruff check`
- 类型检查：`uv run mypy`
- 查看后端日志：`docker compose logs -f backend`

## 当前进行中的需求

- 参见 `docs/PRD.md` 产品需求文档
- 架构决策记录：参见 `docs/adr/` 目录

## Workflow routing

所有任务进站前先分类（详见 docs/openspec-superpowers-实施文档.md §4）：

- **新功能** -> OpenSpec delta 提案（openspec/changes/）-> Superpowers 管线
  （从 writing-plans 进入，跳过 brainstorming）-> 验证 -> sync + archive
- **修 bug · 意图不变** -> 复现测试 + superpowers:systematic-debugging，
  不触碰 openspec
- **修 bug · 意图变更 / 行为未定义** -> 同新功能流程，delta 先行
- **重大架构决策** -> 手动落 docs/adr/（编号递增，只增不改）
- **小改动** -> 直接改

## Spec contract rules

- openspec/specs/ 是系统当前行为的唯一真相来源；修改任何已有行为前必须先查它
- delta 提案是契约的唯一编辑入口；主规范库只能通过 sync 合并更新，禁止手改
- Superpowers 管线的输入是 delta spec，不是对话记录

## Verification red lines

- 没有先写失败测试的代码，删除重写
- archive 前置条件：tasks.md 全勾 + verification 通过 + 人工验证报告落
  tests/validation/
- 「测试全过」不等于「行为正确」；交互行为变更必须有人工验证环节

## Agent skills

### Issue tracker
Issues tracked on GitHub. Use `gh` CLI for all operations. See docs/agents/issue-tracker.md.

### Triage labels
See docs/agents/triage-labels.md.

### Domain docs
Single-context layout - one CONTEXT.md + docs/adr/ at the repo root.
See docs/agents/domain.md. ADR 由人手动维护，agent 不得自动新建 ADR。

## 注意事项

- 排查 bug 时不光要看后端日志，还要查看 Langfuse 的 trace（含 LLM 调用链路、输入输出、耗时与异常），访问地址：http://localhost:3000
- 问题记录和解决方案维护在 `docs/incidents/`，发现系统性问题时新建编号文档并更新 `docs/incidents/README.md` 索引
- 添加新功能前，先检查 `src/finance_agent/` 下是否已有可复用的模块
