# Proposal: add-eval-ops-console

## Why

outcome 评估链（口径协议 / 结算契约 / forward cohort / 回测泄漏控制）落地后，**全部能力都只能通过命令行、环境变量与文档访问**：日批跑没跑只有日志可查、后端漏跑静默不补；cohort 开关与时刻改 env 需重启；回测批、泄漏探针、健康检查是 CLI；回测报告是仓库里的 md；预登记与口径是手改的 markdown。owner 已明确裁决：**上述全部功能都要有可见、可操作的 UI，包括此前建议不做界面的项**（cohort 开关与正式批触发、预登记与口径的编辑、探针与健康检查）。本 delta 把它们统一收进一个「评估运维控制台」。

## What Changes

- **设置中心新增「评估运维」分区**，承载以下全部能力（沿用 `DataMonitorPane` 的 loading/ready/error 状态机）：
  1. **日批调度**：5 个任务（判定/盯市/指标快照/完整性/cohort）的排程、下次触发、最近一次运行（起止/摘要/错误）与运行历史；每任务「立即运行」补跑。
  2. **cohort 控制**：开关 on/off（开启需确认弹窗，展示 ≈1.7M tokens/日 成本估算与当前预算上限）、跑批时刻（时/分）编辑、今日/累计花费与成功率；**即时生效、持久化、重启保持**。
  3. **回测批触发**：界面发起通路验证批 / 正式批；正式批复用既有门禁（有效预登记 + 干净窗口 + 探针披露），门禁不过界面拒绝并展示原因。
  4. **泄漏探针**：对候选窗口单独跑探针并展示三态读数（命中率/未知占比/逐窗口）；回测批报告内的探针段同页展示。
  5. **健康检查**：界面运行 §1.9⑤ 收口健康检查并展示各门禁读数与 FAIL 原因，不静默通过。
  6. **回测报告注册表**：`evals/backtest/results/*.md` 列表 + 生命周期徽章（active/superseded-by）+ 定位标签（通路验证/上界证据）+ 探针读数摘要。
  7. **预登记编辑**：表单化编辑七个门禁字段，保存前跑同一套字段校验；**版本化**（保存生成新版本）；**已有读数的预登记锁定不可改**（防事后改靶）。
  8. **口径查看与受治理编辑**：展示 §1.9 口径表；数值旋钮（判定窗口/中性带/探针阈值/最小样本）的修改**不直接改写台账**，而是生成一份 delta 草稿 + §2 切点行草稿供评审（落 `docs/evals/caliber-drafts/`，不落 `openspec/changes/`），界面明示「生效须走 delta 流程」。
- **战绩页补齐**：总览区渲染回避正确率、当前口径（T+20）、存量旧口径计数（后端已返回、前端未读的三个字段）。
- **运行历史落库**：`job_runs` 表记录每次触发（含 cohort 关闭空转、失败、手动补跑、配置变更审计行）。
- **治理护栏（本 delta 的边界）**：口径/预登记的 UI 是**受治理的编辑入口**而非旁路——预登记保存走版本化与锁定，口径修改只产出 delta 草稿；烧钱动作（cohort 开启、正式批、探针单跑）一律带确认与成本展示，且预算熔断等既有安全语义不变。

## Capabilities

### New Capabilities

- `eval-ops-console`: 评估运维控制台——日批状态与运行历史、手动补跑、cohort 开关/时刻/花费的持久化控制、回测批与探针的界面触发、健康检查界面运行、回测报告注册表、预登记受治理编辑、口径受治理编辑草稿、设置中心运维分区前端。

### Modified Capabilities

- `paper-trading-cohort`: 「成本预算与运维开关」——开关与跑批时刻的唯一真相源由环境变量改为持久化运维配置（env 仅作引导默认），新增界面操作路径；默认关闭/关闭零花费/预算熔断语义不变。
- `track-record`: 「战绩页面（总览 + 观点日志）」——总览区新增回避正确率、当前判定口径、存量旧口径计数三项披露渲染。

## Impact

- 后端：新增 `src/finance_agent/outcome/ops/`（ops_config / job_runs 表、读写与审计）；`scheduler.py` 运行历史埋点 + 运行时重排 + 手动触发；`cohort/runner.py` 开关真相源切换；`api.py` 新增 `/api/v1/ops/*` 端点族；回测/探针/健康检查的**进程内触发封装**（复用既有 CLI 逻辑，不复制实现）。
- 数据库：predictions 所在 SQLite 新增 `ops_config`、`job_runs` 两表（幂等迁移）。
- 前端：`frontend/src/pages/settings/panes/EvalOpsPane.tsx`（新分区）+ `SettingsCenterPage` 注册；`trackRecord/TrackRecordPage.tsx` 总览补齐 + `types.ts` 字段声明。
- 评估侧：`evals/backtest/run_backtest.py`、`evals/backtest/leakage_probe.py`、`evals/outcome/health.py` 增加可被 API 调用的入口封装（行为不变）。
- **交互类变更**：涉及前端 UI → 走 §3 完整管线（E2E 门禁 + 人工验证）。
- 约束沿用：单 uvicorn worker；TESTING=1 调度器不启动、状态接口显式报「未运行」；不新增任何对 `openspec/specs/` 的直接写路径（口径编辑只产出 `docs/evals/caliber-drafts/` 草稿）。
