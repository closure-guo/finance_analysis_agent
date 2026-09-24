# Tasks: add-eval-ops-console

## 1. 运维配置与运行历史存储

- [x] 1.1 `ops_config` / `job_runs` 两表 DDL + 幂等迁移 + 单测（重复迁移不报错、旧库可升级）
- [x] 1.2 配置解析器：表优先 → env 引导默认 → 内置默认；越界/非数值回退 + WARN（沿用 `_env_int` 语义）+ 单测（含「表无值回落 env」「重启保持」）
- [x] 1.3 `cohort/runner.py` 门控切换为解析器（保持「显式参数优先」契约）+ 既有测试全绿

## 2. 运行历史埋点与手动触发

- [x] 2.1 `scheduler._with_retry` 包裹层落 `job_runs`（ok / failed 含重试次数 / skipped-disabled / config-change 旧值→新值）+ 单测
- [x] 2.2 手动触发入口：进程内锁互斥（409 已在运行）、cohort 关时拒绝且零 LLM 调用、结算链补跑幂等 + 单测
- [x] 2.3 运行时重排：cohort 时刻修改即时生效（`reschedule_job`），结算链时刻不受影响 + 单测

## 3. 运维 API 端点族

- [x] 3.1 `GET /api/v1/ops/jobs`：五任务排程/下次触发/最近运行/历史；TESTING 或禁用时显式「未运行」（200，非 500）+ 测试
- [x] 3.2 `POST /api/v1/ops/jobs/{id}/run` + `GET/PUT /api/v1/ops/cohort`（开关/时刻/预算展示/今日花费）+ 审计行 + 测试（含拒绝路径与原因）
- [x] 3.3 `GET /api/v1/ops/reports`（注册表：status 徽章/定位/探针摘要，只读）+ `POST /api/v1/ops/probe`（候选窗口单跑）+ `POST /api/v1/ops/health` + 测试

## 4. 回测批进程内封装

- [x] 4.1 `outcome/ops/batches.py`：抽样→探针→`run_backtest`→落 md/json→记 `job_runs` 的异步任务；正式批先过 `assert_preregistered` + `assert_clean_window`，不过拒绝并带原因 + 测试（门禁拒绝不启动回放）
- [x] 4.2 通路验证批与正式批两条路径的端到端离线测试（fake replay/llm，复用 Δ4 离线驱动的夹具思路）

## 5. 预登记版本化与口径草稿

- [x] 5.1 预登记保存 = 新版本文件 + 同套字段校验拒存 + 单测
- [x] 5.2 读数锁定：被 cohort 读数/回测报告引用的版本只读 + 引导新建版本 + 单测
- [x] 5.3 口径旋钮提交 → 生成 `docs/evals/caliber-drafts/ops-caliber-draft-*` 草稿（proposal/specs/§2 切点行；不落 `openspec/changes/`），**不写** metrics.md 与 caliber.py；同旋钮未处理草稿拒再生成 + 单测（断言台账与常量逐字节未变）

## 6. 前端评估运维分区

- [x] 6.1 `EvalOpsPane.tsx` 六页签 + 状态机（loading/ready/error 重试）+ 未运行横幅 + 组件测试
- [x] 6.2 烧钱确认弹窗统一组件（成本量级 + 预算）；取消不产生任何变更 + 组件测试
- [x] 6.3 门禁拒绝/失败原因的界面展示（非静默）+ 组件测试；`SettingsCenterPage` 注册分区

## 7. 战绩页总览补齐

- [x] 7.1 `types.ts` 补 `avoidance` / `caliber_horizon` / `legacy_settled` 声明
- [x] 7.2 总览渲染三字段：回避正确率与胜率同门槛（<10 显「样本积累中」）、口径常驻、存量计数为 0 显「无存量」+ 组件测试

## 8. 门禁与收口

- [x] 8.1 E2E（交互类门禁）：分区渲染五任务与开关 / 开关确认与取消 / 补跑反馈 / 正式批门禁拒绝展示
- [x] 8.2 人工验证报告落 `tests/validation/`（真实浏览器核对各页签与确认流）
- [x] 8.3 全量范围跑批 + ruff + mypy 触碰文件零新增；`openspec validate add-eval-ops-console --strict`；tasks 勾选与 §2 切点行（交互类 UI 启用切点）

## 依赖与顺序说明

- 前置：`add-forward-paper-trading-cohort`（cohort runner/记账）、`add-backtest-leakage-controls`（门禁与报告生命周期）——即 PR #159 合入后实施；本 delta 分支已自 #159 分支拉出，可并行开发、串行合入。
- Task 1→2→3 为后端主线；4/5 依赖 3；6 依赖 3/4/5 的接口形状；7 独立可并行。
- Owner 决策点：无新增（烧钱安全语义沿用既有熔断与门禁）；界面成本量级估算的数字来源 = 预登记「成本分型」字段。
