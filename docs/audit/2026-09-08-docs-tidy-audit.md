# 文档盘点报告：docs-tidy

**日期**: 2026-09-08
**范围**: `docs/`（102 篇 md）+ 根目录文档（README.md / CONTEXT.md / AGENTS.md）；openspec 主规范库只读盘点；`reports/`、`tmp/`、`.superpowers/` 等产物目录只标记不动内容
**方法**: git 跟踪状态核查 → 全量时效扫描（git log 最后提交日）→ 内部相对链接全量校验（105→106 文件）→ 逐项人工核实
**关联产出**: 本次新建 [docs/README.md](../README.md) 统一索引

---

## 1. 文档全景（盘点时快照）

| 区域 | 数量 | 说明 |
|---|---|---|
| docs/ 根 | 3 | PRD / architecture / project-workflow |
| docs/adr/ | 20 | 0001-0020（只增不改） |
| docs/agents/ | 2 | issue-tracker、triage-labels |
| docs/audit/ | 2 | 2026-08-28 两项归档盘点（本报告为第 3 项） |
| docs/design/ | 9 md + 2 图 | 专项设计档案 |
| docs/evals/ | 4 md + 1 json | 评估体系运行记录 |
| docs/incidents/ | 26 | 001-025 + README 分类索引（索引覆盖完整，无缺漏） |
| docs/superpowers/ | 36 | plans 33 + specs 2 + research 1 |
| openspec/ | 492 跟踪 | specs（28 capability）+ changes（活跃 5 + BACKLOG）+ archive（86） |
| tests/ | 423 跟踪 | validation 报告等 |
| 产物（不入库） | reports/ 339、tmp/、.superpowers/ 92、resume/ | gitignore 覆盖 |

健康结论：**目录职责边界清晰、无孤儿目录、无重复整文件**；主要问题集中在失效链接、过期计数、以及一处机器绝对路径。

## 2. 本次已修复

1. **`docs/adr/0015-langfuse-tracing-integration.md`** — 5 处链接指向已删除的 `src/finance_agent/llm.py`（重构为 `llm/` 包）。全部改为 `src/finance_agent/llm/gateway.py`；正文函数名同步对齐现状（`call_llm` → `complete_text`、`call_llm_stream` → `complete_stream`、`call_llm_with_tools` → `complete_with_tools`），含 Consequences 一节。
2. **`docs/project-workflow.md`** — 3 处 `docs/e2e-implementation.md` 引用（该文件不存在；实际对应 `docs/design/E2E测试实现方案-finance_analysis_agent.md`）。已改为指向真实文件的相对链接（§2 Step 4.5 门禁及 §5.6 落地路线两处）。
3. **`docs/superpowers/specs/2026-07-26-e2e-workflow-integration-design.md`** — 失效输入链接加 `design/` 前缀。
4. **`CONTEXT.md`** — 一处机器绝对路径 `file:///d:\WorkSpace\...` 改为相对路径 `src/finance_agent/prompts`。
5. **`README.md`** — 过期计数：ADR「0001-0017」→「0001-0020」；事故记录「001-022」→「001-025」。文档节置顶新增 [docs 索引](../README.md) 入口。
6. **新建 `docs/README.md`** — docs 全景索引：顶层文档、子目录逐文件导航、权威源约定、维护约定。
7. **清理残留**：`tmp/e2e-reports-8002/`（50M 重复导出物，gitignored）删除；仓库根孤立跟踪文件 `.playwright-cli/page-2026-07-17T07-27-38-190Z.yml`（Playwright 页面捕获残留、无引用）删除。

### 验证

`docs/` 全部 md + 根目录 md 相对链接复扫：修复前 25 处「断裂」→ 修复后真实失效 0 处，剩余为 plans 文档内代码示例/占位符的误报（`{img}`、`path`、`C:/不存在`、`\d{1,2}`、`**operands` 字典解包等），非链接问题。

## 3. 盘点发现（现状健康，无需动作）

- incidents README 分类索引覆盖 001-025 全部条目
- openspec 归档纪律良好（活跃 delta 5 个 + 86 个已归档，与近期「39→10 活跃」清理一致）
- 未跟踪新增（evals/judge_calibration/*）为进行中的校准工作，未动
- `tmp/langfuse-backup/`（1.5M PG dump）为潜在有用的数据库备份，**保留**

## 4. 待人工决策项（本报告未执行）

| 项 | 现状 | 建议 |
|---|---|---|
| `docs/superpowers/plans/` 33 篇 | workflow §5.3 定义「任务级耗材，做完即弃」，但仓库保留全部历史 | 若不再需要可整体归档至 `docs/superpowers/archive/` 或删 git 历史；勿单篇删除。本次未动 |
| `docs/design/` 流状态相关 3 份重叠 | `流状态层重构方案.md` 与 `frontend-stream-state-arch.md`、plans/2026-08-01 resume 计划内容高度相关 | 人工确认各自主次后归档冗余稿 |
| 根目录 `.trae/`、`.claude/` 配置 | 各自 IDE/Agent 配置随仓库跟踪 | 如需收纳到统一工具配置目录可另行清理 |
| `reports/` 339 份运行报告 | gitignore 覆盖的本地产物 | 定期磁盘清理即可，不入库 |

## 5. 后续维护约定

新增/删除/移动文档后同步更新 `docs/README.md` 与根 README「文档」节；本报告与索引互为锚点，`docs/audit/` 保留盘点轨迹。