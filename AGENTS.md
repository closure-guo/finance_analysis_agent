# AGENTS.md — Finance Analysis Agent

LangGraph 多 Agent A 股分析系统：FastAPI 后端 + React 18/Vite 前端。输入股票代码，输出多 Agent 辩论式交易决策报告。

---

## 会话启动（每次会话开始必须先执行）

按以下顺序加载前置依赖：

1. 调用 `using-superpowers` 技能 → 加载 Superpowers 工作流体系
2. 读取 `docs/project-workflow.md` → 获取本项目执行 SOP 地图

---

## 架构速览

- 五层流水线：4 分析师并行 → Bull/Bear 辩论 → Trader 决策 → 风控辩论 → 基金经理批准
- 后端 `src/finance_agent/`（nodes/metrics/data/events/export/harness/prompts）
- 前端 `frontend/`（React + TS + Tailwind + ECharts）
- 链路追踪：Langfuse `http://localhost:3000`
- StreamRegistry 为进程内内存结构 → 后端必须单 uvicorn worker（不可 `--workers N`）
- 架构详情见 `docs/architecture.md`；ADR 见 `docs/adr/`（人工维护，agent 不得新建）

---

## 常用命令

```bash
docker compose up -d --build          # 全栈启动
uv run uvicorn finance_agent.api:app --host 127.0.0.1 --port 8000 --reload  # 后端
cd frontend && npm run dev            # 前端
uv run pytest                         # 后端测试
uv run ruff check                     # Lint
uv run mypy                           # 类型检查
cd frontend && npm test               # 前端测试
```

---

## 任务路由

`project-workflow.md` 是本文档引用的执行 SOP 地图。按下表判定任务类型后，直接跳转该文件对应章节执行。

| 任务类型 | 判别方法 | 动作 | 执行地图 |
|---|---|---|---|
| 新功能 / 行为变更 | 系统新增能力，或 `openspec/specs/` 中行为未定义 | OpenSpec delta + Superpowers | `project-workflow.md` §3 |
| 修 bug · 意图不变 | `openspec/specs/` 已写明正确行为，代码未做到 | systematic-debugging + 复现测试 | `project-workflow.md` §4.1 |
| 修 bug · 意图变更 | `openspec/specs/` 无对应条目，或条目需修改 | 同新功能 | `project-workflow.md` §4.2 |
| 重大架构决策 | 涉及架构层面取舍 | 手动落 `docs/adr/` | — |
| 小改动 | typo / 文案 / 配置 | 直接改 | — |

**交互类变更判别**：delta 涉及前端 UI、SSE 流式、会话切换、状态流转中任一者 → 走 `project-workflow.md` §3 完整管线（含 E2E 门禁）。

---

## 红线（检查清单，不展开）

- [ ] `openspec/specs/` 是系统行为的唯一真相来源；改动前先查；只经 delta 编辑、sync 合并，禁止手改主规范库
- [ ] 没有先写失败测试的代码 → 删除重写
- [ ] 「测试全过」≠「行为正确」；交互行为变更必须有人工验证环节
- [ ] E2E 禁止 mock 被测系统（`route.fulfill` / MSW 拦截业务接口响应 = 红线）；LLM/第三方 API 可用 `TESTING=1` stub，但须配 `@live` 用例 nightly 防漂移
- [ ] archive 前置条件：`tasks.md` 全勾 + verification 通过 + E2E 门禁通过（交互类适用）+ 人工验证报告落 `tests/validation/`
- [ ] 排查 bug 必须同时查后端日志和 Langfuse trace
- [ ] 系统性问题记录到 `docs/incidents/`（编号文档 + 更新 README 索引）
- [ ] Issue 一律用 `gh` CLI；标签规范见 `docs/agents/triage-labels.md`

---

## 测试约束

- E2E（真实浏览器）和集成测试（直连 API）分工明确，详见 `project-workflow.md` §5.6
- 产物位置：fixtures → `tests/fixtures/`｜脚本 → `scripts/`（部署类）与 `tests/scripts/`（测试辅助）｜验证报告 → `tests/validation/`｜E2E 输出 → `tests/e2e/`｜报告 → `reports/`
- 提示词权威源：`src/finance_agent/prompts/*.md`（git 跟踪）是唯一权威源，Langfuse 为部署产物快照；修改 prompt 后必须执行 `uv run python scripts/deploy_prompts.py` 发布，否则 eval 门禁拒绝运行（见 openspec specs/prompt-deploy-consistency）
