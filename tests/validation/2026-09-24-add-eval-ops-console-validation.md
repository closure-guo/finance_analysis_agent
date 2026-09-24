# 人工验证报告: add-eval-ops-console

**日期**: 2026-09-24
**验证人**: agent（机器项 + E2E 门禁 + 真实浏览器走查与截图）
**关联 delta**: openspec/changes/add-eval-ops-console/
**E2E 门禁**: 本 delta 新增 spec `tests/e2e/playwright/tests/eval-ops-console.spec.ts` **5 passed**（exit 0）；stub **全量套件仍红**（14–15 例 LLM 流式家族既有失败，已用基点 worktree 对照归因为既有，见 §门禁归因）。截图与逐项 DOM 文本落 `tests/e2e/ops-console-walkthrough/`（10 张 PNG + `walkthrough-notes.json`）——**注意**：`tests/e2e/.gitignore` 规则 `*.png` 使截图不入库（仓库既定约定，不 force-add），故**本报告引用的 PNG 是本机工作树产物**；`walkthrough-notes.json`（机器可读的逐项实测文本）随本报告入库，构成可复查的入库证据。

## 范围说明（读表前必读）

本 delta 把 outcome 评估链此前只能经 CLI / 环境变量 / 手改 markdown 访问的能力，收进设置中心「评估运维」分区（六页签）并落成可操作界面：日批五任务状态与运行历史、手动补跑、cohort 开关与跑批时刻（持久化 + 即时重排）、回测批与泄漏探针触发、outcome 收口健康检查、回测报告注册表、预登记版本化与口径受治理编辑；另补战绩页总览三项披露。**9 条 requirement（7 ADDED + 2 MODIFIED）共 38 个 Scenario 全部有落点。**

**验证分层（诚实声明）**：

- **机器项**：范围跑批 `652 passed, 2 deselected`（exit 0）+ ruff 零违例 + ruff format 触碰文件全过 + mypy 触碰文件零新增（4 例全落在本分支零改动的 `evals/extract.py`）+ 前端 `618 passed` + `openspec validate --strict` 通过。
- **E2E 门禁（真实浏览器 + TESTING=1 真后端，零业务接口 mock）**：新增 spec 5 例覆盖「分区渲染五任务与未运行横幅 / 开关确认与取消零写入 / 正式批拒绝展示原因 / 手动补跑落终态 / cohort 关闭拒绝手动跑批」，**5 passed**。**stub 全量套件非全绿**，红的是 LLM 流式家族既有失败（下详），非本 delta 引入。
- **人工浏览器走查**：真实 Chromium 逐页签核对六页签渲染、未运行横幅、cohort 确认弹窗（成本估算 + 预算上限）、取消路径、正式批拒绝原因、手动补跑终态，并截图存证。**本轮走查由 agent 执行且图像已由模型直接视觉审阅**（对照 add-agent-settings-center 报告的「截图待人工复核」缺口，本轮无此限制）。
- **不声称**：真实 LLM 探针 / 回测正式批 / cohort 跑批（属 owner 预算门控项）；成本估算与真实的对照；多 worker 行为。逐条见 §未验证项。

## 门禁归因（为什么 stub 全量套件是红的）

| 运行 | 命令 | 结果 |
|---|---|---|
| 本 delta 新增 spec（单跑） | `npx playwright test eval-ops-console.spec.ts` | **`5 passed (29.2s)`**，exit 0 |
| 全量 stub 门禁（HEAD） | `npx playwright test` | `14 failed, 19 passed, 1 skipped (2.9m)`，exit 1 |
| 全量 stub 门禁（**去掉新 spec**） | 同上，spec 移出后 | `15 failed, 12 passed`，exit 1 |
| 全量 stub 门禁（**分支基点 worktree** `743ea80`） | 同上，独立 worktree + 独立 venv | `14 failed, 13 passed, 2 skipped`，exit 1 |

**结论**：红的 14–15 例全部属同一家族（`streaming` / `thinking-banner` / `search-banner` / `agui-chat` / `interaction` / `deep-thinking-toolcall` / `concurrent-streaming-integrity`），失败形态是 `agui-stream-status` 不消失 / `思考中` 按钮不出现，即**流式终态未到达**；本机无 LLM key 且 Langfuse 不可达（日志实测 `prompt quick_mode 拉取失败，回退本地`、`WinError 10061`）。**基点 worktree 同样红 → 既有失败，非本 delta 引入**；家族内个别用例逐轮翻转（如 `streaming.spec.ts:87` 在基点红、终轮绿；`concurrent-streaming-integrity.spec.ts:134` 相反），属该家族既有的不稳定。**本 delta 未删除、未放宽任何既有断言**（红线遵守；新增 spec 的断言强度不变，仅放大时间预算，见 §异常记录②）。

## Scenario 对照表（38 Scenario / 9 requirement）

### R1 日批运行状态与历史可观测（ADDED，3 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 1 | 五任务状态齐备 | `src/finance_agent/ops_api.py::_jobs_payload`（L333）/ `_job_rows`（L311）/ `GET /jobs`（L396）；`outcome/ops/jobs.py::JOB_IDS`（L47）/ `SCHEDULES`（L76） | `tests/test_ops_api.py::test_last_run_and_history_shape`（L302）、`test_history_is_bounded_and_newest_first`（L329）；E2E「分区渲染五任务卡片与「调度器未运行」显式横幅」（五卡片逐一断言排程/下次触发/最近一次运行）；走查实测五卡片 `mon-fri 16:00/16:30/16:35/16:40/18:00（Asia/Shanghai）` | ✅ |
| 2 | 调度器未启动显式态 | `ops_api.py::_scheduler_running`（L205）/ `_next_fire_time`（L217）/ `_degraded_jobs_payload`（L354） | `tests/test_ops_api.py::test_reports_not_running_under_testing`（L290）、`test_mock_handle_does_not_claim_running`（L1129）、`test_degraded_payload_on_unexpected_db_error`（L405）；E2E 断言 `scheduler_running=false` 下横幅与「—（调度器未运行或未注册）」占位（不冒充时间）；截图 `01-tab-schedule.png` | ✅ |
| 3 | 空转与失败均留痕 | `outcome/ops/jobs.py::run_job`（L146）+ `outcome/ops/model.py::insert_job_run`（L263）/ `finish_job_run`（L296）；`outcome/scheduler.py::_with_retry`（L63）/ `_mark_retries`（L102） | `tests/outcome/test_ops_jobs.py::test_run_job_records_failed_with_error`（L71）、`test_cohort_scheduled_disabled_records_skip_without_raising`（L209）；`tests/test_ops_api.py::test_last_run_takes_newest_of_retry_attempts`（L311）；`tests/outcome/test_scheduler.py::test_scheduled_failure_lands_in_history_with_retries`（L362）；走查实测 cohort 卡片「空转（开关关闭）· reason=switch_off」 | ✅ |

### R2 手动补跑（ADDED，3 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 4 | 结算链补跑（幂等） | `ops_api.py::trigger_job`（L406）；`ops/jobs.py::run_job`（L146） | `tests/outcome/test_ops_jobs.py::test_run_job_records_ok_with_summary`（L61）；幂等由既有 `tests/outcome/test_job.py::test_idempotent_no_double_settle`（L90）与 `tests/outcome/test_track_record_job.py`（L220 幂等说明）覆盖；E2E「手动补跑完整性校验…」+ 走查实测 `run_id=13 kind=manual status=ok finished_at=2026-09-24T20:08:07.469399` | ✅ |
| 5 | cohort 关闭时拒绝手动跑批（零 LLM） | `ops/jobs.py::CohortDisabled`（L114）+ run_job 门控；`ops_api.py` 409 `cohort_disabled` | `tests/test_ops_api.py::test_cohort_disabled_409_and_zero_llm`（L535）；`tests/outcome/test_ops_jobs.py::test_cohort_manual_run_refused_when_disabled`（L193）；**E2E「cohort 关闭时手动跑批被拒绝」**断言横幅含「cohort 开关未开启」且运行历史留 `skipped-disabled` 行 | ✅ |
| 6 | 并发互斥 | `ops/jobs.py::JobAlreadyRunning`（L110）+ 每任务 `_LOCKS`；`mark_run_active`（L128）/ `active_run_ids`（L140） | `tests/outcome/test_ops_jobs.py::test_run_job_is_single_flight`（L111）、`test_lock_is_per_job`（L173）、`test_lock_released_after_failure`（L134）；`tests/test_ops_api.py::test_already_running_409`（L526）、`test_same_kind_concurrent_refused`（L814） | ✅ |

### R3 cohort 开关与时刻的界面控制（ADDED，4 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 7 | 开启需确认并审计 | `frontend/.../EvalOpsPane.tsx::onToggleCohort`（L419）/ `askSpend`（L336）；`ConfirmSpendDialog.tsx`（dialog L29 / cost L39 / budget L42）；`ops_api.py::update_cohort`（L486）+ `_apply_cohort_update`（L455） | `tests/test_ops_api.py::test_put_persists_reschedules_and_audits`（L563）、`test_put_records_audit_even_without_scheduler`（L596）；`frontend/src/test/settings/evalOpsPane.test.tsx:277`（确认含成本与预算）、`:297`（确认后提交并展示审计）；**E2E「cohort 开关切换先确认…」** + 走查实测弹窗文案「≈1.7M tokens/日」「当前预算上限：2,000,000 tokens」（截图 `04-cohort-confirm-dialog.png`） | ✅ |
| 8 | 关闭即时零花费 | `ops/jobs.py::run_job` cohort 门控（关闭 → 记 `skipped-disabled` 且不调 runner）；`outcome/cohort/runner.py`（L107–110） | `tests/outcome/test_ops_jobs.py::test_cohort_manual_run_refused_when_disabled`（L193）；`tests/outcome/test_cohort_runner.py::test_config_table_disabled_beats_env_enabled`（L681）；`tests/outcome/test_scheduler.py::test_scheduled_cohort_disabled_records_skip_without_calling_runner`（L427） | ✅ |
| 9 | 时刻修改即时重排 | `outcome/scheduler.py::reschedule_cohort`（L224）/ `_apply_cohort_schedule`（L160）；`ops_api.py::_apply_cohort_update`；前端 `saveCohortTime`（L432）+ `eval-ops-cohort-audit`（L744） | `tests/outcome/test_scheduler.py::test_moves_next_fire_and_clears_on_stop`（L492）、`test_returns_false_when_no_scheduler`（L480）、`test_rejects_out_of_range`（L485）；`tests/test_ops_api.py::test_put_partial_update_keeps_other_keys`（L584）、`test_put_rejects_out_of_range`（L590）；`tests/outcome/test_ops_jobs.py::test_settlement_chain_schedules_unchanged`（L39，结算链四任务时刻不受影响） | ✅ |
| 10 | 重启保持 | `ops/model.py::bootstrap_cohort_from_env`（L204）/ `get_cohort_settings`（L183）；`src/finance_agent/api.py` lifespan（L75–78） | `tests/outcome/test_ops_model.py::test_bootstrap_writes_env_values_only_when_absent`（L118）、`test_bootstrap_keeps_existing_table_value_over_env`（L139）、`test_cohort_settings_table_wins_over_env`（L68）；`tests/test_ops_api.py::test_lifespan_bootstraps_cohort_config_from_env`（L1104） | ✅ |

### R4 回测批与探针的界面触发（ADDED，4 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 11 | 无有效预登记时界面拒绝正式批 | `ops_api.py::_preflight_formal`（L687）+ `POST /backtest` 409（L708）；前端本地预检 `submitBacktest`（L499–520）+ `eval-ops-backtest-refusal`（L794） | `tests/test_ops_api.py::test_backtest_formal_refused_without_preregistration`（L664）；`frontend/.../evalOpsPane.test.tsx:346`（本地预登记无效 → 零请求）；**E2E 覆盖到「正式批发起被拒且原因可见」的通用契约**（见 §未验证项①：本 worktree 预登记存在且有效，409 预登记分支在 stub 环境不可达） | ⚠️ 见① |
| 12 | 通路验证批可触发 | `ops/batches.py::run_backtest_task`（L200）/ `prepare_backtest`（L115）；`ops_api.py::trigger_backtest` | `tests/test_ops_api.py::test_backtest_pathway_returns_202_and_trimmed_summary`（L608）、`test_pathway_offline_end_to_end_writes_report`（L900）；`tests/outcome/test_ops_batches.py::test_pathway_batch_returns_report_and_writes_md` | ✅ |
| 13 | 探针单跑读数展示（三态） | `ops/batches.py::run_probe_task`（L265）；`ops_api.py::trigger_probe`（L742）+ `_trim_probe_summary`（L585）；前端 `ProbeResult`（L999，`eval-ops-probe-state` L1007） | `tests/test_ops_api.py::test_probe_returns_readings_without_details`（L732）、`test_probe_offline_end_to_end`（L944）；`tests/outcome/test_ops_batches.py::test_probe_task_marks_unmeasurable`；`frontend/.../evalOpsPane.test.tsx:437`（不可测态展示「不可测」而非 0） | ✅ |
| 14 | 报告注册表展示状态与定位 | `ops_api.py::_reports_payload`（L512）/ `_positioning_of`（L495）/ `_probe_hit_rate_of`（L506）；前端 `ReportTable`（L1110） | `tests/test_ops_api.py::test_registry_reads_status_header`（L981）、`test_registry_reads_positioning_and_probe_rate`（L998）、`test_registry_missing_dir_is_empty_not_error`（L1035）、`test_registry_flags_defective_report_loudly`（L1039）；走查实测一行 `pilot-2023-shock / 生效中 / 通路验证 / —`（截图 `08-tab-reports.png`） | ✅ |

### R5 健康检查界面运行与展示（ADDED，2 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 15 | 门禁不过显式 FAIL | `ops/batches.py::run_health_task`（L364）/ `_gate_row`（L323）；前端 `HealthResult`（L1038，`eval-ops-health-verdict` L1072） | `tests/test_ops_api.py::test_health_dispatch_passes_gates_summary`（L780）、`test_health_run_uses_real_collector`（L927）；`frontend/.../evalOpsPane.test.tsx:470`（FAIL + 实测/阈值）、`:496`（0.11 vs ≤10.0% 常量被测试钉住） | ✅ |
| 16 | 读数缺失如实展示 | `ops/batches.py::_no_readings_payload`（L348）；前端 `HealthResult` 无读数分支（L1046） | `frontend/.../evalOpsPane.test.tsx:522`（无读数不冒充 0%/100%）；`tests/outcome/test_ops_batches.py::test_health_task_is_json_serializable` | ✅ |

### R6 预登记与口径的受治理编辑（ADDED，4 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 17 | 预登记缺字段拒绝保存 | `ops/prereg.py::save_prereg_version`（L97）/ `InvalidPreregistration`（L64）；`ops_api.py::save_prereg`（L808） | `tests/outcome/test_ops_prereg.py::test_save_rejects_invalid_fields_without_touching_disk`（L61）、`test_save_rejects_bare_threshold_without_rationale`（L70）；`tests/test_ops_api.py::test_put_rejects_missing_fields_without_writing`（L1243）、`test_put_rejects_bare_threshold_without_rationale`（L1256）；`frontend/.../evalOpsPane.test.tsx:611` | ✅ |
| 18 | 已有读数的预登记锁定 | `ops/prereg.py::is_locked`（L241）/ `_backtest_references`（L170）/ `_cohort_readings_lock`（L197）；`ops_api.py` 409 `locked` | `tests/outcome/test_ops_prereg.py::test_lock_detects_reading_reference`（L150）、`test_lock_degrades_to_any_success_cohort_run`（L175）、`test_lock_without_readings_is_false_and_creates_nothing`（L166）；`tests/test_ops_api.py::test_put_refuses_locked_base_version_and_writes_nothing`（L1264）、`test_lock_flips_when_backtest_report_references_version`（L1204）；`frontend/.../evalOpsPane.test.tsx:624`（只读 + 锁定原因 + 引导新建版本） | ✅ |
| 19 | 口径修改生成 delta 草稿而非直接改台账 | `ops/prereg.py::write_caliber_draft`（L448）+ `_render_proposal`（L388）/ `_render_spec_skeleton`（L313）/ `_render_timeline_line`（L363）；`ops_api.py::create_caliber_draft`（L868） | `tests/outcome/test_ops_prereg.py::test_caliber_draft_does_not_touch_ledger_or_constants`（L267）、`test_caliber_draft_files_are_the_three_required_artifacts`（L282）、`test_second_draft_for_same_knob_refused`（L327）；`tests/test_ops_api.py::test_draft_created_then_refused_for_same_knob`（L1330）；`frontend/.../evalOpsPane.test.tsx:642`（明示「草稿待评审」）；**本轮实测生成草稿**（`LEAKAGE_PROBE_THRESHOLD 0.6→0.55` → `openspec/changes/ops-caliber-draft-20260924-200458/{proposal.md,specs/evaluation/spec.md,metrics-timeline-line.md}`，台账与 `caliber.py` 零改动，草稿已删） | ✅（草稿 validate 见残留风险③） |
| 20 | 编辑留审计 | `ops_api.py::_save_prereg_with_audit`（L781）/ `_draft_with_audit`（L847） | `tests/test_ops_api.py::test_put_saves_new_version_and_audits`（L1218）、`test_put_without_base_path_keeps_create_new_version_semantics`（L1298）；`tests/outcome/test_ops_prereg.py::test_save_writes_new_version_without_touching_history`（L78） | ✅ |

### R7 评估运维分区前端（ADDED，3 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 21 | 分区渲染五任务与开关 | `frontend/.../SettingsCenterPage.tsx`（nav L24 / 挂载 L103）；`EvalOpsPane.tsx`（pane L661 / 未运行横幅 L664 / 页签 L688）；`trackRecord` 之外的 `eval-ops-cohort-summary`（L671） | **E2E 用例 1**；`frontend/.../evalOpsPane.test.tsx:141`、`:158`（运行中不显示横幅 + 下次触发）；`frontend/.../settingsCenterPage.test.tsx:698`（导航注册）；走查截图 `01-tab-schedule.png` | ✅ |
| 22 | 开关确认弹窗 | `EvalOpsPane.tsx::askSpend`/`cancelSpend`（L336–350）；`ConfirmSpendDialog.tsx`（L29/L39/L42/L48） | **E2E 用例 2**（确认含成本与预算；取消后开关不变 + 服务端状态与审计行数均不变）；`frontend/.../evalOpsPane.test.tsx:277`（取消零请求）、`:409`（正式批取消零请求）、`:423`（探针取消零请求） | ✅ |
| 23 | 门禁拒绝的界面展示 | `EvalOpsPane.tsx::eval-ops-error`（L681）/ `runRefusalText`（L142）/ `eval-ops-backtest-refusal`（L794） | **E2E 用例 3**（正式批 422 前置拒绝原因可见 + 报告注册表零新报告）、**E2E 用例 5**（cohort 关闭 409 拒绝原因可见 + `skipped-disabled`）；`frontend/.../evalOpsPane.test.tsx:361`（服务端 409 门禁拒绝展示原因，不静默/不转圈）、`:249`、`:259`（手动补跑拒绝与 500 详情可见） | ✅ |

### MODIFIED：paper-trading-cohort「成本预算与运维开关」（5 Scenario）

| # | Scenario | 落点 | 证据 | 通过 |
|---|---|---|---|---|
| 24 | 默认关闭 | `ops/model.py::COHORT_DEFAULT_ENABLED`（L36）+ `get_cohort_settings`（L183） | `tests/outcome/test_ops_model.py::test_cohort_settings_all_default_when_table_and_env_empty`（L87）；E2E 用例 1 断言 `eval-ops-cohort-enabled` = 「未开启」；走查截图 | ✅ |
| 25 | 预算超限熔断 | **一行不改**（沿用既有 `cohort/runner.py` 熔断 + 记账）；`ops_api.py::_cohort_block`（L297）只读展示预算/今日花费 | 既有 `tests/outcome/test_cohort_runner.py`（含 `test_unknown_usage_trips_budget_unknown` L569）；范围跑批 652 passed 未回归 | ✅（语义未动） |
| 26 | 成本随轮落账 | **一行不改**（沿用 cohort usage 真值记账）；`ops_api.py::_today_cohort_stats`（L281）只读汇总 | 既有 cohort 记账用例；走查实测 cohort 花费行「今日花费 0 tokens · 预算上限 2,000,000 tokens · 今日成功 0 · 失败 0」 | ✅（语义未动） |
| 27 | 界面开关持久化与即时生效 | 前端 cohort 页签（L712–755）+ `ops_api.py` `PUT /cohort`（L486）+ `scheduler.reschedule_cohort`（L224） | `tests/test_ops_api.py::test_put_persists_reschedules_and_audits`（L563）、`test_put_partial_update_keeps_other_keys`（L584）；`tests/outcome/test_scheduler.py::test_cohort_hour_minute_from_config_table_beats_env`（L457）；E2E 用例 2（取消路径）；**「保存时刻/确认开启」的写路径未在浏览器实点**（见 §未验证项②） | ⚠️ 见② |
| 28 | 关闭空转留痕 | `ops/jobs.py::run_job` 关闭分支；`scheduler.py::_with_retry` | `tests/outcome/test_ops_jobs.py::test_cohort_scheduled_disabled_records_skip_without_raising`（L209）；`tests/outcome/test_scheduler.py::test_scheduled_cohort_disabled_records_skip_without_calling_runner`（L427）；E2E 用例 5 断言 `skipped-disabled` 行；走查实测卡片「空转（开关关闭）」 | ✅ |

### MODIFIED：track-record「战绩页面（总览 + 观点日志）」（10 Scenario）

| # | Scenario | 本 delta 是否触碰 | 落点 / 证据 | 通过 |
|---|---|---|---|---|
| 29 | **回避正确率披露** | ✅ 新增 | `frontend/src/pages/trackRecord/TrackRecordPage.tsx::track-record-avoidance`（L272）；`frontend/src/types.ts` 补 `avoidance`/`caliber_horizon`/`legacy_settled` | `frontend/src/test/trackRecord/trackRecordPage.test.tsx:568`（充足时展示率与样本数）、`:577`（不足显「样本积累中」）、`:592`（后端给率即照实展示）、`:621`（读数缺失不显 0%） | ✅ |
| 30 | **口径与存量计数披露** | ✅ 新增 | `TrackRecordPage.tsx::track-record-caliber`（L304）/ `track-record-legacy`（L307）/ `track-record-caliber-row`（L303） | `trackRecordPage.test.tsx:604`（常驻 + 存量为 0 显「无存量」）、`:612`（存量 >0 显条数与未计入声明） | ✅ |
| 31 | 页面渲染总览与观点日志 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:98` | ✅（范围跑批未回归） |
| 32 | 默认视图不可隐藏 loss | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:98` | ✅ |
| 33 | 回避终态标签渲染 | ➖ 未触碰（回归） | `predictionStatus.ts`；既有 `trackRecordPage.test.tsx:423` | ✅ |
| 34 | 展示建立日期列 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:312` | ✅ |
| 35 | 按列排序交互 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:320` | ✅ |
| 36 | 关键字过滤交互 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:345` | ✅ |
| 37 | 时间段过滤交互 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:367` | ✅ |
| 38 | 过滤后分页浏览 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:388` | ✅ |
| （附） | 空态与样本不足 / 数据缺口不伪造 | ➖ 未触碰（回归） | 既有 `trackRecordPage.test.tsx:89`、`:115` | ✅ |

## 机器验证结果

分支 `feat/batch-ops-console`，工作树 `.worktrees/ops-console`，HEAD `c1e06a6` + 本任务改动。

| 命令 | 真实输出摘要 | 判定 |
|---|---|---|
| `uv run pytest tests/outcome tests/test_ops_api.py tests/evals/backtest -q -m "not live"` | `652 passed, 2 deselected, 44 warnings in 594.86s (0:09:54)`（exit 0） | ✅ 范围全绿 |
| `uv run ruff check evals/ src/ tests/` | `All checks passed!` | ✅ 零违例 |
| `uv run ruff format --check <本 delta 触碰的 16 个 .py>` | `16 files already formatted` | ✅ |
| `uv run mypy src/finance_agent/outcome/ops src/finance_agent/ops_api.py` | `Found 4 errors in 1 file (checked 6 source files)` | ✅ 触碰文件零新增（4 例全在 `evals/extract.py`：`git diff --name-only 743ea80 HEAD -- evals/extract.py` → 0 行，该文件最后改动在 #127，属既有；mypy 顺 import 检查到它） |
| `cd frontend && npm test` | `Test Files 75 passed (75)` / `Tests 618 passed (618)` / `Duration 56.39s` | ✅ 全绿 |
| `openspec validate add-eval-ops-console --strict` | `Change 'add-eval-ops-console' is valid` | ✅ |
| `openspec validate --all --strict`（无草稿目录时） | `Totals: 56 passed, 0 failed (56 items)` | ✅ |
| `openspec list` | `add-eval-ops-console 0/22 tasks`（勾选前） | ✅ |

## 人工浏览器走查结果（真实 Chromium + TESTING=1 真后端）

截图与逐项 DOM 文本落 `tests/e2e/ops-console-walkthrough/`（`walkthrough-notes.json` 为机器可读原始记录，入库；PNG 因 `tests/e2e/.gitignore` 的 `*.png` 规则仅存本机）。入口：`/settings` → 左导航「评估运维」（与 add-agent-settings-center 同款入口；header/侧栏「设置」按钮均跳 `/settings`）。

| 页签 | 实测所见 | 截图 | 通过 |
|---|---|---|---|
| 入口/设置中心 | 左导航七分区含「评估运维」；点击后右侧挂载分区 | `00-settings-center.png` | ✅ |
| 调度 | **未运行横幅**：「调度器未运行（TESTING=1 或显式禁用）：定时触发不会执行，任务行可手动补跑；配置改动重启后生效。」；cohort 摘要条「未开启 / 跑批时刻 18:00（Asia/Shanghai）/ 今日花费 0 / 预算 2,000,000 tokens」；五卡片各含排程 + 下次触发（`—（调度器未运行或未注册）`）+ 最近一次运行 + 立即运行 | `01-tab-schedule.png` | ✅ |
| 调度（手动补跑） | 点「立即运行」→ 卡片刷新为新行 `成功 · 2026-09-24T20:08:07.469399 · checked=0 · mismatches=[] · mismatch_count=0`；服务端 `run_id=13 kind=manual status=ok`（`finished_at` 与卡片文本逐字一致） | `02-manual-run-terminal.png` | ✅ |
| cohort | 开关未勾选（未开启）；花费行「今日花费 0 tokens · 预算上限 2,000,000 tokens · 今日成功 0 · 失败 0」；时刻输入 18 / 0 + 保存时刻 | `03-tab-cohort.png` | ✅ |
| cohort（确认流） | 勾开关 → 弹窗「确认开启 cohort 跑批」+ 说明「该动作会产生 LLM 调用与 token 花费…取消不产生任何变更。」+ 成本估算「规模：每日一轮 cohort 跑批（默认 universe），≈1.7M tokens/日」+ 预登记「成本分型」原文（含来源路径）+「当前预算上限：2,000,000 tokens（今日已花费 0 tokens）」；**取消后开关回到未勾选**，服务端 cohort 状态与审计行数零变化（E2E 用例 2 断言） | `04-cohort-confirm-dialog.png` | ✅ |
| 回测与探针 | 预登记预检行「预登记门禁预检：evals/ablation/preregister/2026-09-23-outcome-forward-and-backtest.md（字段齐备）」；标的输入 + 每 regime 抽样 / 重复次数 + 通路验证批 / 正式批；探针表单（代码 / 决策日 / 抽样只数） | `05-tab-backtest.png` | ✅ |
| 回测与探针（**门禁拒绝**） | 填 `600519` 点「正式批」→ 确认 → 红色横幅「**回测批发起被拒绝：regime bull 标的池不足 10**」（服务端 422 真实原因，非 mock、非前端文案）；无结果卡、无「后台执行中」、报告注册表零新报告 | `06-formal-refusal.png` | ✅ |
| 健康检查 | 「outcome 收口健康检查（只读；读数缺失展示「无读数」）」+「运行健康检查」+ 初始「尚未运行——点右上「运行健康检查」。」 | `07-tab-health.png` | ✅ |
| 报告注册表 | 表头 报告/状态/定位/探针方向命中率；一行 `pilot-2023-shock / 生效中 / 通路验证 / —` | `08-tab-reports.png` | ✅ |
| 预登记与口径 | 最新版本 + 「字段齐备」+ 七字段表单 + 保存为新版本 / 新建版本 + 「校验与 CLI 同一套（…磁盘零改动）」；口径旋钮四行（判定窗口 20 / 中性带 0.02 / 探针阈值 0.6 / 最小已结算样本 10）+「现值只读自 evals/outcome/caliber.py」+ 生成 delta 草稿 | `09-tab-prereg-caliber.png` | ✅ |

**视觉核验**：全部截图已由模型直接看图审阅——布局无重叠/错位/溢出，未运行横幅与 cohort 摘要条配色区分清晰，弹窗浮层不透明且遮罩生效，表格与表单对齐正常。（**教训**：首次截图为动画中帧，`getComputedStyle` 实测 `opacity: 0`（`fade-in-0` 动画未收敛）导致画面看似「浮层透明、底层文案透出」；等 `toHaveCSS('opacity','1')` 后重截即正常——**不是产品缺陷**，记录以免后人误判。）

## 未验证项（诚实声明）

1. **E2E 未覆盖「无有效预登记 → 拒绝正式批」这一具体 GIVEN**：本 worktree 的 `evals/ablation/preregister/2026-09-23-outcome-forward-and-backtest.md` 存在且字段齐备（走查实测预检行如此显示），故 **409 预登记门禁分支在 stub 环境不可达**（前端本地预检也不会触发）。E2E 用例 3 因此锚定「正式批发起被拒 + 原因取自真实服务端响应 + 未启动任何回放」这一**可复现的拒绝可见性契约**（实测为 422 前置拒绝 `regime bull 标的池不足 10`）；409 预登记与干净窗口两条门禁分支由 `tests/test_ops_api.py::test_backtest_formal_refused_without_preregistration`（L664）与 `::test_backtest_formal_clean_window_refusal_409`（L680）+ 组件测试 `evalOpsPane.test.tsx:346/361` 覆盖。**这不是断言放宽**：E2E 里「原因必须来自真实 DOM/真实响应、且拒绝前不得启动回放」的强度不变。
2. **界面的写路径未在浏览器实点**：cohort「确认开启」、保存跑批时刻、预登记保存、口径草稿生成、健康检查运行、通路批/探针发起——本轮走查只做只读核对与**取消**路径（取消 = 零写入，是刻意的：避免在测试库留下开启态与真实花费）。这些写路径由 `tests/test_ops_api.py`（含离线端到端）与 `evalOpsPane.test.tsx` 覆盖，但**没有真实浏览器点击 → 落库 → 回显**的闭环证据。
3. **真实 LLM / 花费路径一概未跑**：探针单跑（真 LLM 答题）、回测正式批（回放 + 探针）、cohort 跑批（≈1.7M tokens/日）——全部属 **owner 预算门控项**，本报告不声称其可用。
4. **成本估算与真实的对照未做**：弹窗展示的「≈1.7M tokens/日」来自预登记「成本分型」字段（pilot 实测 ≈166k tokens/标的 × 10 标的），**本轮零实际调用**，估算准确性未验证。
5. **多 worker 行为未验证**：全局约束是单 uvicorn worker（StreamRegistry 与 APScheduler 均 in-process）；手动触发互斥只用进程内锁。多 worker 下互斥与 `reschedule_cohort` 的正确性**未测**（也不在本 delta 目标内）。
6. **非 light 主题与移动端**：走查只用默认（浅色）主题 + 1440×960 视口；暗色主题下六页签与弹窗的对比度未核。
7. **cohort 已开启态的界面**：`eval-ops-cohort-enabled` = 「已开启」分支、审计行「已记配置变更审计行 #N · 已即时重排调度」文案、以及「已开启」时点「立即运行」的真实跑批，均未在浏览器观察。

## 残留风险（reviewers / implementers 报告，本 delta 未消除）

1. **探针 `per_window` 合成**：单窗口调用下逐窗口读数的合成逻辑（终审修复轮改动点）只在单测/离线脚本里验证过，无真实探针跑批对照。
2. **prune-on-poll**：状态接口读到悬挂 `running` 行时就地收尾并顺带 `prune_job_runs(keep_per_job=500)`——即**「轮询」这个读操作会写库**（含裁剪）。这是为防历史表膨胀的刻意设计（且不另记审计行，避免轮询制造膨胀），但意味着 `/api/v1/ops/jobs` 不是纯读接口；并发轮询下的写锁竞争未做压测。
3. **`ops-caliber-draft-*` 目录**：本轮实测生成草稿后 `openspec validate --all --strict` **由 `56 passed, 0 failed` 变 `56 passed, 1 failed`**——报错 `evaluation/spec.md: MODIFIED "Outcome 收益指标口径与预登记" must contain SHALL or MUST`（骨架只有标题与场景，未填 MUST 条文）；`openspec list` 仍可用但会把草稿列成一个 change（`No tasks`）。**草稿存在期间会拖红仓库级 strict 校验**，需后续让骨架自带合法 MUST 句，或在评审流程里明确「草稿未过 strict 属预期」。草稿已删，`--all --strict` 已回到 56/0。
4. **阈值字面同步**：`EvalOpsPane.tsx` 把 `MIN_SETTLEMENT_SUCCESS_RATE = 0.90` / `MAX_UNRESOLVABLE_RATE = 0.10` / `COHORT_DAILY_ESTIMATE = '≈1.7M tokens/日'` 硬编码为展示用常量（注释声明与后端字面同步），**非单一真相源**——后端改阈值时前端需同步手改（组件测试 `evalOpsPane.test.tsx:496` 已把该字面钉住，改动会被测出）。
5. **前端从不发 `base_path`**：`PUT /api/v1/ops/prereg` 支持可选 `base_path` 以对指定版本做锁定判定（服务端 409 `locked`），但**界面不发该字段**，故「已有读数的预登记锁定」在界面上只能靠列表里的 `locked` 标记走「新建版本」路径；服务端 409 分支在界面**不可达**（仅单测覆盖）。属接口留白，不是缺陷，但界面语义弱于 spec 措辞。
6. **E2E 环境的时间预算**：全量套件并行时（本机 15+ 个流式 spec 争抢）单 worker 后端与 vite dev 冷启动会把「分区就绪」拉到 20–60s，新增 spec 因此用 describe 级 120s 预算 + 网络断言 30s/60s 超时。**断言强度未变**，但意味着该 spec 在重载环境里会慢；若 CI 更慢需再评估。
7. **`EvalOpsPane` 加载占位态无 testid**：`jobs === null` 时渲染纯文本「评估运维加载中…」（无 `data-testid`），E2E 只能等 ready 态的 `eval-ops-pane`——这是本次把超时放宽的直接原因，加一个 `eval-ops-loading` testid 可让等待更精确（未改，属前端 Task 6 范围）。
8. **`not.toHaveText` 类断言的假绿陷阱（本轮实测踩到）**：走查脚本首版用「文本变了」判断补跑生效，因 Playwright `toHaveText` 的空白归一化与 `innerText()` 不一致而**瞬间假绿**（DOM 其实还没刷新）。已改为「用服务端 `finished_at` 时间戳精确锚定卡片文本」，门禁 spec 同步修正。

## 结论

- [x] 全部 Scenario 有落点（38/38；其中 #11 的 GIVEN 在 stub 环境不可达，已用可复现的拒绝可见性契约 + 单测/组件测试补足，见 §未验证项①）
- [x] 本 delta 新增 E2E spec 5 passed；机器项（范围跑批 / ruff / format / mypy 触碰文件 / 前端测试 / openspec strict）全过
- [x] 人工浏览器走查完成，六页签 + 未运行横幅 + 确认取消 + 门禁拒绝 + 手动补跑终态均有截图与 DOM 证据
- [ ] **stub 全量套件未全绿**：14–15 例 LLM 流式家族既有失败（基点 worktree 同样红，非本 delta 引入，未删未放宽断言）——**需 owner 决策**：是承认该家族在本机/CI 既有红并放行本 delta，还是先立 issue 修该家族（本项目 incident 023 明确反对「带红合并」与「retry 能过就算 flaky」的错误归因，故此处显式登记而不掩盖）
- [ ] 真实 LLM 探针 / 回测正式批 / cohort 跑批：转 owner 预算门控（本报告不声称）
