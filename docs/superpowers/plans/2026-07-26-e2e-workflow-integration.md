# E2E 门禁融入项目工作流（F1 文档重构）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 E2E 门禁（Step 4.5）重构进 docs/project-workflow.md，并在 AGENTS.md 补一条 archive 前置条件，使文档自洽地描述「交互类变更 ①→⑥ 含 E2E 门禁」的完整管线。

**Architecture:** 纯文档重构，不改任何代码。以设计文档 `docs/superpowers/specs/2026-07-26-e2e-workflow-integration-design.md` 为唯一输入；project-workflow.md 做 10 处定点修改，AGENTS.md 做 1 处定点修改。TDD 在此不适用（无代码），验证方式为文档自洽性检查（grep 断言关键内容存在且锚点编号正确）。

**Tech Stack:** Markdown 文档。

## Global Constraints

- 唯一真相来源：`docs/superpowers/specs/2026-07-26-e2e-workflow-integration-design.md`（下称「设计文档」），改动内容必须与它逐字一致，不得临场发挥
- 只改两个文件：`docs/project-workflow.md`、`AGENTS.md`；禁止顺手改其他文档
- E2E 门禁生效过渡语必须保留：「E2E 门禁自 F2（基础设施）完成之日起强制执行；此前交互类变更沿用原人工验证流程」
- §4 Bug 修复流程、§6 并行变更规则不得改动
- Commit 信息中文，格式 `docs: <改动点>`
- 代码注释/文档语言：中文

---

### Task 1: project-workflow.md 全景图 + 路由表 + Step 1/2 改动

**Files:**
- Modify: `docs/project-workflow.md`（§1 全景图 9-55 行、§2 路由表 61-70 行、§3 Step 1 tasks.md 模板 127-133 行、§3 Step 2 操作 154-161 行）

**Interfaces:**
- Consumes: 设计文档 §2（管线结构）、§4（改动清单前四行）
- Produces: §1/§2/§3-Step1/§3-Step2 的新文本，供 Task 2 的 Step 4.5 衔接

- [ ] **Step 1: §1 全景图插入 ④.5 节点**

将 §1 全景图中 `④ Superpowers: verification-before-completion` 代码块之后、`⑤ 人工验证` 之前的部分：

```
  │  ④ Superpowers: verification-before-completion               │
  │     运行验证命令 → 读取输出 → 确认通过 → 才能声称完成        │
  │                    │                                         │
  │                    ▼                                         │
  │  ⑤ 人工验证                                                    │
```

替换为：

```
  │  ④ Superpowers: verification-before-completion               │
  │     运行验证命令 → 读取输出 → 确认通过 → 才能声称完成        │
  │                    │                                         │
  │                    ▼                                         │
  │  ④.5 E2E 门禁（仅交互类变更）                                 │
  │     cd tests/e2e/playwright && npx playwright test           │
  │     全绿 → 进 ⑤；红 → 打回 ③，禁止带病进人工验证           │
  │                    │                                         │
  │                    ▼                                         │
  │  ⑤ 人工验证（抽查 + 主观项确认）                               │
```

- [ ] **Step 2: §2 路由表「新功能」行更新 + 新增判别说明**

将 §2 路由表中「新功能」行：

```
| 新功能 | 系统新增能力 | ①→⑥ 完整管线 | 全程 |
```

替换为：

```
| 新功能 | 系统新增能力 | ①→⑥ 完整管线（交互类含 ④.5 E2E 门禁） | 全程 |
```

并在路由表下方追加一段：

```markdown

**交互类变更判别**：delta 涉及前端 UI、SSE 流式、会话切换、状态流转中任一者，即为交互类变更，走 ④.5 E2E 门禁；纯后端逻辑变更（指标计算、数据管道、prompt 调整）不适用 ④.5。
```

- [ ] **Step 3: §3 Step 1 tasks.md 模板加 E2E 验收项示例**

将 §3 Step 1 工件 4 tasks.md 模板代码块：

````markdown
```markdown
# Tasks: <change-id>

- [ ] 验收项 1（如「流式中断恢复可用」）
- [ ] 验收项 2（如「会话切换时 SSE 正确断开重连」）
- [ ] 验收项 3（如「人工验证报告已落 tests/validation/」）
```
````

替换为：

````markdown
```markdown
# Tasks: <change-id>

- [ ] 验收项 1（如「流式中断恢复可用」）
- [ ] 验收项 2（如「会话切换时 SSE 正确断开重连」）
- [ ] E2E spec 已覆盖本变更的核心交互场景（仅交互类变更）
- [ ] 验收项 4（如「人工验证报告已落 tests/validation/」）
```
````

- [ ] **Step 4: §3 Step 2 操作列表加 E2E 任务卡要求**

将 §3 Step 2 操作第 3 条：

```
3. 每个任务包含：文件路径、接口契约、TDD 五步（写失败测试 → 运行确认失败 → 写最小实现 → 运行确认通过 → 提交）
```

替换为：

```
3. 每个任务包含：文件路径、接口契约、TDD 五步（写失败测试 → 运行确认失败 → 写最小实现 → 运行确认通过 → 提交）
   - 交互类变更必须拆出 E2E spec 任务卡：先写失败的 Playwright spec（tests/e2e/playwright/tests/*.spec.ts）→ 实现 → spec 转绿，与单测同一 TDD 纪律。spec 写作红线见 §5.5
```

- [ ] **Step 5: 验证文档自洽性**

Run（PowerShell）:

```powershell
Select-String -Path docs/project-workflow.md -Pattern "④.5 E2E 门禁" | Measure-Object | Select-Object -ExpandProperty Count
Select-String -Path docs/project-workflow.md -Pattern "交互类变更判别" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "E2E spec 已覆盖本变更的核心交互场景" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "E2E spec 任务卡" -Quiet
```

Expected: Count ≥ 1；三个 Quiet 检查均输出 True。

- [ ] **Step 6: Commit**

```bash
git add docs/project-workflow.md
git commit -m "docs: workflow 全景图与计划阶段接入 E2E 门禁（Task 1/3）"
```

---

### Task 2: project-workflow.md 新增 Step 4.5 节 + Step 5/6 更新

**Files:**
- Modify: `docs/project-workflow.md`（§3 Step 4 之后插入新节、Step 5 人工验证 329-359 行、Step 6 archive 前置条件 365-372 行）

**Interfaces:**
- Consumes: Task 1 已插入的全景图 ④.5 节点（本节是它的展开）；设计文档 §2（Step 4.5 定义）、§4（改动清单 5-7 行）
- Produces: 完整的 Step 4.5 节文本；更新后的 Step 5/6

- [ ] **Step 1: 在 Step 4 与 Step 5 之间插入 Step 4.5 完整一节**

在 `### Step 5: 人工验证` 标题之前，插入以下整节：

````markdown
### Step 4.5: E2E 门禁（仅交互类变更）

**触发条件**: delta 涉及交互行为（前端 UI、SSE 流式、会话切换、状态流转，判别无 §2）。

**生效过渡**: E2E 门禁自 F2（门禁基础设施）完成之日起强制执行；此前交互类变更沿用原人工验证流程，本节可跳过。

**操作**:

```bash
cd tests/e2e/playwright && npx playwright test
```

stub 套件（后端以 `TESTING=1` 启动，LLM 走可控 stub），确定性、秒级-分钟级完成。

**通过标准**: 全绿。

**失败处理**: 任一 spec 红 → 打回 Step 3 修复，禁止带病进人工验证。失败证据（trace、截图）在 `tests/e2e/playwright/playwright-report/`，可用 playwright-debugger skill 诊断。

**证据要求**: playwright-report 路径记入验证材料（人工验证报告 §异常记录 引用）。

**红线**: 禁止为了让门禁变绿而删除或放宽断言——断言被改弱必须能在 diff 中解释原因。
````

- [ ] **Step 2: Step 5 人工验证改为「抽查 + 主观项」**

将 §3 Step 5 整节（从 `### Step 5: 人工验证` 到 `### Step 6` 之前）替换为：

````markdown
### Step 5: 人工验证

**触发条件**: 任何交互行为变更（前端 UI、SSE 流式、会话切换、状态流转）。

**操作**:
1. E2E 已覆盖的 Scenario：抽查确认（不必逐条手测，E2E 门禁已挡低级错误）
2. E2E 覆盖不到的主观项（LLM 报告内容质量、整体体验）：逐条人工验证
3. 记录验证结果到 `tests/validation/YYYY-MM-DD-<change-id>-validation.md`

**模板**:

```markdown
# 人工验证报告: <change-id>

**日期**: YYYY-MM-DD
**验证人**: [姓名]
**关联 delta**: openspec/changes/<change-id>/
**E2E 门禁**: [playwright-report 路径 / 不适用]

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 会话切换时 SSE 断开重连 | 是（streaming.spec.ts） | 切换后旧连接断开，新会话建立新连接 | 抽查符合 | ✅ |
| 报告内容无明显幻觉 | 否 | 关键财务数据与来源一致 | 逐条核对符合 | ✅ |

## 异常记录
（如有失败项，记录复现步骤和实际行为）

## 结论
[ ] 全部通过，可 archive
[ ] 存在失败项，需修复后重新验证
```

> 人工验证的定位：E2E 看人会漏的（交互状态机、流式生命周期），人看机器看不了的（LLM 输出质量、整体体验）。两者是互补，不是重复。
````

- [ ] **Step 3: Step 6 archive 前置条件加 E2E 门禁**

将 §3 Step 6 前置条件代码块：

```
□ openspec/changes/<change-id>/tasks.md 全部勾选
□ Superpowers verification-before-completion 已通过
□ 人工验证报告已落 tests/validation/
□ openspec validate <change-id> --strict 通过
```

替换为：

```
□ openspec/changes/<change-id>/tasks.md 全部勾选
□ Superpowers verification-before-completion 已通过
□ E2E 门禁通过（交互类变更适用）
□ 人工验证报告已落 tests/validation/
□ openspec validate <change-id> --strict 通过
```

- [ ] **Step 4: 验证文档自洽性**

Run（PowerShell）:

```powershell
Select-String -Path docs/project-workflow.md -Pattern "Step 4.5: E2E 门禁" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "禁止带病进人工验证" | Measure-Object | Select-Object -ExpandProperty Count
Select-String -Path docs/project-workflow.md -Pattern "E2E 门禁通过（交互类变更适用）" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "E2E 已覆盖？" -Quiet
```

Expected: 全部 True；Count ≥ 2（全景图一次 + Step 4.5 节一次）。

- [ ] **Step 5: Commit**

```bash
git add docs/project-workflow.md
git commit -m "docs: workflow 新增 Step 4.5 E2E 门禁节，人工验证改为抽查+主观项（Task 2/3）"
```

---

### Task 3: project-workflow.md §5.5/§5.2/§7 + AGENTS.md 配套 + 全文档终验

**Files:**
- Modify: `docs/project-workflow.md`（§5 新增 5.5 小节、§5.2 tasks.md 模板 487-495 行、§7 速查表 531-546 行）
- Modify: `AGENTS.md`（「契约与红线」节 32 行）

**Interfaces:**
- Consumes: 设计文档 §6（E2E 写作红线原文）；Task 1/2 已落位的 ④.5 引用
- Produces: F1 最终交付物；全文档自洽

- [ ] **Step 1: §5 新增 5.5 小节「E2E spec 写作红线」**

在 §5.4 progress ledger 小节之后、§6 并行变更规则之前，插入：

````markdown
### 5.5 E2E spec 写作红线

写 E2E spec 任务卡（Step 2）和审查 spec 代码（Step 3）时的检查清单：

```markdown
- ❌ 禁止恒真断言：`toBeDefined()` / `assert locator is not None`（P0）
- ❌ 禁止 expect 缺 await（P0）
- ❌ 禁止手动取值后断言（P1，用 web-first assertion 自动重试）
- ❌ 禁止条件绕过：`if (await x.isVisible()) { 断言 }`（P1）
- ❌ 禁止 `waitForTimeout` 赌时序（用 expect 自动重试或等具体事件）
- ❌ 禁止 route.fulfill / MSW 伪造业务接口响应（AGENTS.md 红线；LLM/第三方 `TESTING=1` stub 除外）
- ✅ selector 必须来自真实浏览器快照（data-testid / role+name 优先）
- ✅ 断言稳定的终态，不断言过渡过程
- ✅ 故障注入用 route.abort()，合法且推荐
```
````

- [ ] **Step 2: §5.2 tasks.md 模板同步加 E2E 验收项**

将 §5.2 模板代码块：

````markdown
```markdown
# Tasks: <change-id>

- [ ] 验收项 1（粗粒度，如「SSE 流式中断恢复可用」）
- [ ] 验收项 2（如「会话切换时旧连接正确断开」）
- [ ] 验收项 3（如「人工验证报告已落 tests/validation/」）
```
````

替换为：

````markdown
```markdown
# Tasks: <change-id>

- [ ] 验收项 1（粗粒度，如「SSE 流式中断恢复可用」）
- [ ] 验收项 2（如「会话切换时旧连接正确断开」）
- [ ] E2E spec 已覆盖核心交互场景（仅交互类变更）
- [ ] 验收项 4（如「人工验证报告已落 tests/validation/」）
```
````

- [ ] **Step 3: §7 速查表新增三行**

在 §7 表格最后一行 `| Bug fix: 一个 PR 只修一个 Bug，先写复现测试 | 用户规则 |` 之前，插入三行：

```
| 交互类变更必须过 E2E 门禁（Step 4.5），红则打回禁止带病进人工验证 | workflow §3 Step 4.5 |
| stub 套件（TESTING=1）跑门禁，@live 套件（真 LLM）nightly 防漂移 | AGENTS.md 测试约束 |
| E2E spec 写作红线（P0/P1 反模式） | workflow §5.5 |
```

- [ ] **Step 4: AGENTS.md「契约与红线」补 E2E 门禁前置条件**

将 AGENTS.md 第 32 行：

```
  - archive 前置条件：tasks.md 全勾 + verification 通过 + 人工验证报告落 `tests/validation/`
```

替换为：

```
  - archive 前置条件：tasks.md 全勾 + verification 通过 + E2E 门禁通过（交互类变更适用）+ 人工验证报告落 `tests/validation/`
```

- [ ] **Step 5: 全文档终验（F1 验收标准：自洽走查）**

Run（PowerShell）:

```powershell
# 关键内容存在性
Select-String -Path docs/project-workflow.md -Pattern "Step 4.5: E2E 门禁" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "5.5 E2E spec 写作红线" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "交互类变更必须过 E2E 门禁" -Quiet
Select-String -Path AGENTS.md -Pattern "E2E 门禁通过（交互类变更适用）" -Quiet
# 不得改动的章节保持原样
Select-String -Path docs/project-workflow.md -Pattern "4.1 A 类: 意图不变" -Quiet
Select-String -Path docs/project-workflow.md -Pattern "6. 并行变更规则" -Quiet
# 生效过渡语保留
Select-String -Path docs/project-workflow.md -Pattern "自 F2（门禁基础设施）完成之日起强制执行" -Quiet
```

Expected: 全部 True。

再执行一次人工走查：从「一个交互类新功能进站」的视角通读 project-workflow.md ①→⑥，确认每一步衔接无断点（④.5 触发条件在 §2 有判别、Step 4.5 有操作、Step 6 有对应前置条件）。

- [ ] **Step 6: Commit**

```bash
git add docs/project-workflow.md AGENTS.md
git commit -m "docs: workflow §5.5 E2E 红线 + §7 速查 + AGENTS.md archive 前置条件补 E2E 门禁（Task 3/3）"
```

---

## Self-Review 记录

- **Spec 覆盖**：设计文档 §4 改动清单 10 行 → Task 1（§1/§2/Step1/Step2）+ Task 2（Step 4.5/5/6）+ Task 3（§5.5/§5.2/§7/AGENTS.md），逐行有归属；§5 分期中 F1 即本计划全部任务 ✅
- **占位符扫描**：无 TBD/TODO，每步含实际替换文本 ✅
- **类型一致性**：「④.5 E2E 门禁」「交互类变更」「E2E 门禁通过（交互类变更适用）」等术语在三个 Task 间逐字一致 ✅
