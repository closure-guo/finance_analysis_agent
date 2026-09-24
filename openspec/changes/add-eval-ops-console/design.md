# Design: add-eval-ops-console

## D1 配置真相源：持久化 ops_config，env 仅引导

新增 `ops_config(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)` 于 predictions 所在 SQLite（同连接模式，幂等迁移）。键：`cohort_enabled` / `cohort_hour` / `cohort_minute`。启动时若键不存在，以环境变量（`COHORT_ENABLED` / `COHORT_HOUR` / `COHORT_MINUTE`，沿用 `_env_int` 的越界回退）写入作引导默认；运行期读写只认表。`cohort/runner.py` 的门控改为读解析器 `ops.get_cohort_enabled()`（表优先、表无值回落 env），保持「参数显式传入优先」的既有测试契约不变。

**为什么不用改 env + 重启**：界面操作要求即时生效与重启保持，env 两者都不满足；而把真相源放表里后，env 仍保留运维兜底入口（表损坏/未初始化时）。

## D2 运行历史：job_runs + 统一埋点

`job_runs(id INTEGER PK, job_id TEXT, kind TEXT, started_at, finished_at, status TEXT, summary TEXT, error TEXT)`。`scheduler._with_retry` 包裹层落行：`status ∈ {ok, failed, skipped-disabled, running, config-change}`；cohort 空转、失败重试次数、手动补跑、配置变更（旧值→新值）均落行。手动触发与定时触发走同一包裹层，天然互斥由 D3 的进程内锁保证。

**不做**跨进程锁：单 uvicorn worker 是既有硬约束（StreamRegistry / scheduler in-process），进程内 `dict[job_id, Lock]` 足够；多 worker 部署本就不被支持，spec 不承诺。

## D3 手动触发与烧钱安全

`POST /api/v1/ops/jobs/{job_id}/run`：校验 job_id 白名单 → 取进程内锁（已被占用 → 409「已在运行」）→ 线程内执行包裹层 → 返回 run id；状态经 `GET /api/v1/ops/jobs` 的最近运行轮询。cohort 的 run 在包裹层内先查开关：关 → 记 `skipped-disabled` 并 409 拒绝（零 LLM 调用）。结算链四任务幂等（既有语义），补跑安全。预算熔断、串行、usage 真值等既有安全语义**一行不改**。

## D4 回测 / 探针 / 健康检查的进程内封装

不复制 CLI 逻辑：`evals/backtest/run_backtest.py` 的 `run_backtest` 与 `run_batch_probe`、`evals/backtest/leakage_probe.run_leakage_probe`、`evals/outcome/health.collect_outcome_health` 均已可导入。新增薄服务层 `src/finance_agent/outcome/ops/batches.py`：把「抽样 → 探针 → run_backtest → 落 md/json → 记 job_runs」串成异步任务（线程），返回 run id；正式批在发起前先跑 `assert_preregistered` + `assert_clean_window`，不过即拒绝（原因进响应与 job_runs）。报告注册表 = 扫 `evals/backtest/results/*.md` 的 status 头与定位句（复用 `status_index.collect_status_index` + 报告内字段），只读。

**成本明示**：正式批与探针单跑是真 LLM 消耗；界面确认弹窗展示样本数 × 回放次数 × 探针题量的量级估算（数字来自预登记的「成本分型」字段），后端不做额外硬限（预算熔断只管 cohort）。

## D5 预登记编辑：版本化 + 读数锁定

保存 = 写**新文件**（沿用 `YYYY-MM-DD-<name>.md` 命名与 `find_latest_preregister` 的取最新语义），历史版本不覆盖。锁定判定：任一 cohort 读数或回测报告的 `preregister.path` 指向该版本 → 该版本只读，界面引导「新建版本」。表单校验复用 `parse_preregister(..., required_fields=OUTCOME_REQUIRED_FIELDS)`（缺字段 / 决策阈值缺换算依据 → 拒存），与 CLI 门禁同一实现，不另造校验。

## D6 口径编辑：只产 delta 草稿，不碰台账与常量

界面提交数值旋钮（判定窗口 / 中性带 / 探针阈值 / 最小已结算样本）→ 生成 `openspec/changes/ops-caliber-draft-<ts>/`（proposal 片段 + `specs/evaluation` delta 片段 + §2 切点行草稿），**不写** `docs/evals/metrics.md`、不写 `evals/outcome/caliber.py`；界面展示草稿路径与「生效须走 delta 流程（validate → 评审 → sync）」。同一旋钮已有未处理草稿时拒绝再生成。这把「编辑界面」变成**受治理的起草入口**：owner 要的是可见可操作，项目红线要的是口径变更走评审，两者在此兼容。

## D7 前端：EvalOpsPane 与子页签

设置中心新增分区 `EvalOpsPane.tsx`，子页签：调度 / cohort / 回测与探针 / 健康检查 / 报告注册表 / 预登记与口径。状态机沿用 `DataMonitorPane`（loading / ready / error + 重试）；异步任务轮询 `GET /api/v1/ops/jobs`。烧钱动作确认弹窗统一组件（展示成本量级 + 当前预算）。调度器未运行时整区顶部显式横幅。战绩页总览补齐三字段（`types.ts` 声明 + 渲染，回避正确率与胜率同门槛）。

## D8 测试与门禁

单元：ops 表迁移幂等、解析器优先级（表 > env > 默认）、重排即时性、并发互斥、锁定判定、草稿生成不碰台账。API：状态显式未运行态、cohort 关时 run 拒绝、门禁拒绝原因、审计行。前端组件：页签渲染 / 确认弹窗取消不变更 / 门禁拒绝展示。E2E（交互类门禁）：分区渲染五任务与开关、开关确认与取消、补跑反馈、正式批门禁拒绝展示。人工验证：真实浏览器核对各页签与确认流，报告落 `tests/validation/`。

## Risks / Trade-offs

- [界面让烧钱动作变容易] → 确认弹窗 + 成本量级展示 + cohort 关时 run 拒绝 + 预算熔断不变；正式批门禁不变。
- [口径草稿被误当已生效] → 界面明示 + 草稿目录命名带 `draft` + 不写台账/常量；validate 仍须人工跑。
- [job_runs 无限增长] → 保留最近 N 行（默认 500/任务）的滚动清理，清理本身记审计。
- [单 worker 约束被未来部署破坏] → 既有约束，本 delta 不改变；多 worker 下手动触发互斥失效属部署违规，spec 不承诺。
