# E2E 门禁融入项目工作流 · 设计文档

> 日期：2026-07-26
> 输入：[E2E测试实现方案-finance_analysis_agent.md](../../E2E测试实现方案-finance_analysis_agent.md) + [project-workflow.md](../../project-workflow.md) + AGENTS.md 新版测试约束红线
> 目标：把 E2E 方案从一份孤立的技术方案，重构为项目工作流的正式门禁环节

---

## 1. 背景与冲突消解

### 1.1 现状

- 工作流（project-workflow.md）是 OpenSpec + Superpowers 六步管线，人工验证（Step 5）是交互类变更的唯一行为级验证手段，无自动化 E2E 环节
- 现有 `tests/e2e/` 为 pytest + Python sync Playwright，两类资产混杂：
  - 真 LLM 慢链路（如 test_5layer_pipeline.py）——直接调 `build_5layer_graph()`，不经浏览器，本质是集成测试
  - 浏览器交互脚本（e2e_*.py）——截图存档式，断言纪律弱，无 web-first 断言
- AGENTS.md 新版测试约束已明确：
  - 拦截伪造业务接口响应（route.fulfill / MSW）= 红线
  - LLM、第三方 API 可用 `TESTING=1` stub，**但须配 @live 用例**（nightly 跑真实服务防漂移）
  - 故障注入（route.abort()）不算 mock

### 1.2 关键冲突与消解

| 冲突 | 消解方式 |
|---|---|
| 方案新建根目录 `e2e/` vs 项目规则禁止根目录新建测试目录 | TS Playwright 项目落 `tests/e2e/playwright/` |
| 方案的 LLM stub vs 旧红线「E2E 禁止 mock」 | AGENTS.md 新版已许可 `TESTING=1` stub + @live 配套，本设计将其落成工作流纪律 |
| 方案的 `backend/main:app` 路径 vs 本项目实际 | 按实际修正为 `uv run uvicorn finance_agent.api:app` |
| Python pytest E2E vs TS Playwright 双栈 | 分层迁移（见 §3），不全部重写 |

---

## 2. 管线结构变更（核心设计）

在现有六步管线中插入 **Step 4.5 E2E 门禁**，并把 E2E 测试写作前移到 Step 2 计划阶段：

```
① OpenSpec delta 提案
   └─ 新增要求：交互行为变更的 delta，tasks.md 必须含
      「E2E spec 已覆盖本变更的核心交互场景」
② writing-plans
   └─ 新增要求：交互类任务的计划必须包含 E2E spec 任务卡
      （先写失败的 E2E spec → 实现 → 转绿，与单测同一 TDD 纪律）
③ subagent-driven-development（不变）
④ verification-before-completion（不变，含 pytest + 单测）
④.5 【新增】E2E 门禁
   ├─ 触发条件：delta 涉及交互行为（前端 UI / SSE 流式 / 会话切换 / 状态流转）
   ├─ 运行 stub 套件：cd tests/e2e/playwright && npx playwright test
   ├─ 全绿 → 进入 Step 5；红 → 打回 Step 3 修复，禁止带病进人工验证
   └─ 证据：playwright-report 路径记入验证材料
⑤ 人工验证（降级但保留）
   └─ E2E 已覆盖的 Scenario 抽查确认 + E2E 覆盖不到的主观项
      （LLM 报告内容质量、整体体验）逐条人工确认
⑥ sync + archive
   └─ 前置条件新增：E2E 门禁通过记录（仅交互类变更适用）
```

**核心逻辑**：E2E 不替代人工验证，而是替人工验证挡住低级错误——人只看机器看不了的（LLM 输出质量、整体体验），机器看人会漏的（交互状态机、流式生命周期）。

**生效过渡**：E2E 门禁自 F2（基础设施）完成之日起强制执行；此前交互类变更沿用原人工验证流程。

---

## 3. 测试分层与目录结构

```
tests/
├── e2e/                        # 现有目录，重新定位
│   ├── live/                   # @live 套件（真 LLM 慢链路，nightly 触发）
│   │   └── test_5layer_pipeline.py 等   ← 从现位置迁入，重新分类为集成测试
│   ├── playwright/             # 【新增】TS Playwright 项目（E2E 门禁主体）
│   │   ├── package.json
│   │   ├── playwright.config.ts         # 双 webServer 拉起前后端
│   │   ├── tests/
│   │   │   ├── smoke.spec.ts            # 冒烟：页面可达
│   │   │   ├── streaming.spec.ts        # SSE 流式核心链路（stub 确定性断言）
│   │   │   ├── contract.spec.ts         # 前后端网络契约
│   │   │   └── interaction.spec.ts      # 交互状态（禁用/loading/CSS 终态）
│   │   └── playwright-report/           # gitignored，失败证据 + trace
│   └── *.png / report_*.md              # 存量截图与报告（gitignored，随旧脚本退役清理）
├── fixtures/  scripts/  validation/     # 不变
```

**三个关键决策**：

1. **不新建根目录 `e2e/`**——TS 项目落 `tests/e2e/playwright/`，遵守产物位置红线
2. **双套件分工**——stub 套件（`TESTING=1`，确定性，PR/门禁触发）+ `@live` 套件（真 LLM，nightly 触发，防 stub 与真实 LLM 行为漂移）。`pytest -m live` 可独立触发
3. **故障注入合法**——`page.route` + `route.abort()` 模拟断连不算 mock（红线原文），中断恢复场景写进 streaming.spec.ts

**存量迁移决策（已确认不做全部 TS 重写）**：真 LLM 链路用 TS 重写是降级——会失去直接 import Python graph、断言内部状态的能力，只能黑盒断言最终报告。因此保留为 Python @live 套件；仅浏览器交互脚本分批重写为 TS spec，完成后旧脚本归档到 `tests/scripts/`。

---

## 4. project-workflow.md 改动清单

| 章节 | 改动 |
|---|---|
| §1 全景图 | ④ 和 ⑤ 之间插入 `④.5 E2E 门禁（交互类变更）` 节点；⑤ 人工验证描述改为「抽查 + 主观项确认」 |
| §2 任务路由表 | 「新功能」行路由列改为 `①→⑥ 完整管线（交互类含 ④.5 E2E 门禁）`；新增交互类变更判别说明 |
| §3 Step 1 | tasks.md 模板新增示例：`- [ ] E2E spec 已覆盖核心交互场景（仅交互类变更）` |
| §3 Step 2 | 新增操作：交互类任务必须拆出 E2E spec 任务卡（同走 TDD 五步：先写失败的 spec → 实现 → 转绿） |
| §3 新增 Step 4.5 | 完整一节：触发条件 / 运行命令 / 通过标准 / 失败处理（打回 Step 3）/ 证据要求（report 路径） |
| §3 Step 5 人工验证 | 触发条件不变；操作改为：E2E 已覆盖的 Scenario 抽查 + 覆盖不到项逐条验证；模板加列「E2E 已覆盖？」 |
| §3 Step 6 | archive 前置条件硬关卡新增：`□ E2E 门禁通过（交互类变更适用）` |
| §5 新增 5.5 | 「E2E spec 写作红线」小节，作为写 spec 任务卡的检查清单（内容见 §6） |
| §5.2 tasks.md 模板 | 同步加 E2E 验收项示例 |
| §7 关键规则速查 | 新增三行：E2E 门禁规则、stub/@live 分层规则、E2E 反模式红线 |

**不改动的**：§4 Bug 修复流程（E2E 复现测试可作为 A 类 bug 的复现手段但不强制，避免拖慢 hotfix）、§6 并行变更规则。

**配套**：AGENTS.md「契约与红线」archive 前置条件补一句 E2E 门禁，保持与 workflow 一致。

---

## 5. 落地分期与验收标准

按「workflow 文档先行，基础设施跟上」分期——先立规矩再补工具：

| 期 | 内容 | 验收标准 |
|---|---|---|
| **F1 文档重构**（本次直接交付物） | 改写 project-workflow.md（§4 全部改动点）+ AGENTS.md 补 E2E 门禁前置条件 | 文档自洽：任一交互类变更进站，能照文档走完 ①→⑥ 不卡壳 |
| **F2 门禁基础设施** | `tests/e2e/playwright/` 初始化、双 webServer、后端 `/health` 端点、`TESTING=1` LLM stub、smoke.spec 跑通 | `npx playwright test` 一条命令拉起全栈并跑绿 smoke |
| **F3 核心 spec + 存量迁移** | streaming/contract/interaction 三个 spec；真 LLM 链路迁入 `tests/e2e/live/` 打 @live 标记；旧截图脚本归档 `tests/scripts/` | 断开后端 streaming.spec 变红（门禁有牙）；`pytest -m live` 可独立触发 |
| **F4 CI + 工具链** | GitHub Actions（stub 套件 PR 触发，@live nightly）；e2e-skills（scan/reviewer/generator/debugger） | PR 上 E2E 自动跑，失败有 trace artifact；存量 spec P0 反模式清零 |

**范围控制（YAGNI）**：F1 是本次重构交付物；F2-F4 是后续实施任务，各自走独立 OpenSpec delta 提案（它们本身是新功能）。本次只定义规矩，不代做基础设施。

**风险与对策**：

- F1 先于 F2 的空窗期「文档要求跑 E2E 但跑不了」→ 文档注明门禁自 F2 完成起强制执行
- stub 与真 LLM 行为漂移 → @live nightly 套件作漂移哨兵，这是分层结构存在的意义

---

## 6. E2E spec 写作红线（落入 workflow §5.5）

```markdown
- ❌ 禁止恒真断言：`toBeDefined()` / `assert locator is not None`（P0）
- ❌ 禁止 expect 缺 await（P0）
- ❌ 禁止手动取值后断言（P1，用 web-first assertion 自动重试）
- ❌ 禁止条件绕过：`if (await x.isVisible()) { 断言 }`（P1）
- ❌ 禁止 `waitForTimeout` 赌时序（用 expect 自动重试或等具体事件）
- ❌ 禁止 route.fulfill / MSW 伪造业务接口响应（项目红线，LLM/第三方 stub 除外）
- ✅ selector 必须来自真实浏览器快照（data-testid / role+name 优先）
- ✅ 断言稳定的终态，不断言过渡过程
- ✅ 故障注入用 route.abort()，合法且推荐
```

---

## 7. 已确认的决策记录

| 决策点 | 结论 |
|---|---|
| E2E 接入方式 | 作为人工验证前置门禁（Step 4.5），不替代人工验证 |
| 存量 pytest E2E | 分层迁移：真 LLM 链路 → @live 套件保留 Python；浏览器交互脚本 → 分批重写 TS |
| 真 LLM 链路是否 TS 重写 | 否（会失去 graph 内部状态断言能力，降级为黑盒） |
| 落地顺序 | 文档先行（F1），基础设施跟上（F2-F4 各自走 delta 提案） |
