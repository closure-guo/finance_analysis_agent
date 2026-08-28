# 验证记录: harden-evaluation-rigor

**日期**: 2026-08-28
**验证人**: ZCode agent（SDD 控制器；人工门禁项见文末待办）
**关联 delta**: openspec/changes/harden-evaluation-rigor/
**分支**: feat/harden-evaluation-rigor（d9208bc..ec3156c，14 commits）
**E2E 门禁**: 不适用（纯后端/评估设施变更，非交互类）

## 自动化门禁（新鲜运行）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 测试 | `uv run pytest -m "not live" -q` | **1381 passed / 2 skipped / 8 deselected**，0 失败 |
| 测试（含 live） | `uv run pytest -q` | 4 失败均为 `@live` 网络用例（AKShare/真实 LLM），main 基线既有环境现象，与本 delta 无关（历届 ledger 同记录） |
| Lint | `uv run ruff check`（delta 全部文件） | All checks passed（仓级 11 错全部位于会话前已存在的未跟踪 scripts/evals_gated_run.py 与 scripts/observe_langfuse_experiments.py，非本 delta 产物） |
| 类型 | `uv run mypy src/` | 69 errors = 基线 d9208bc 位级一致（worktree 实测），本 delta 改动的 citation.py/citation_node.py 0 错 |
| 类型 | `uv run mypy evals/` | 1 error = evals/run.py:75 `read_text(newline=)` 存量（先于本 delta，CI 只跑 `mypy src/ || true`） |
| 准度 CLI | `uv run python -m evals.claim_benchmark.accuracy` | 种子集 33 条实测 P/R/F1=1.0、f1_ci=[1.0,1.0]、borderline/hedged 分项披露、gate_passed=true |
| 种子可重生成 | 重跑 `_seed_gen` 后 `git diff` | seed.jsonl/meta.json 位级一致（确定性） |

## 契约对照结论（逐 Requirement 终审矩阵通过）

- **citation-verification**：注册表 7 根键全覆盖（每根键 fixture 重算测试）；未注册根键 → UNVERIFIABLE + coverage_gaps 计数；`citation_unverifiable_ratio` Score 上报（未配置/失败均 WARN 不阻断）；容差（0.01/0.5%）与三态裁决零回归（既有测试全绿）。突升监控（detect_rise +10pp 可配）与告警落盘可用。
- **evaluation**：基准集 schema（双人标注字段 + 仲裁 + κ 计算 + 版本约定）与 33 条确定性种子集交付；准度测量 FAIL-正类 P/R/F1 + bootstrap 95% CI + 0.90 门禁 + 擦边/hedged 双口径（FAIL 召回 + 子集一致率）披露；对比 CLI 配对 bootstrap B=10,000，结论措辞结构性三选一（CI 含 0 → 只能"无显著差异"）；消融三变体（与主图逐边同构，快照对齐 digest 为证）层间增量 judge 分数 + citation_pass 率均带 CI，CI 含 0 → "该层价值未获统计支持"。
- **decision-backtest**：时点截断（K 线/财报按法定披露截止/宏观按月/新闻事件按日；纯当下数据剔除并记录）经真实数据格式验证（横线报告日/「日期」列名/datetime 键）；快照审计元信息含 data_cutoff/disclosure_rule/prompt_versions/model；四指标 + 四基线（无前视 T-1 信号）；分层抽样缺 regime 抛错；block bootstrap + 块长敏感性 + Sharpe>3 拦截；n=3 一致率 per_symbol 全量披露；结算直调 outcome.settle.evaluate_decision（零复制）。

审查过程：11 轮任务级 spec 审查 + 1 轮全分支终审 + 1 轮终审复核；3 个任务经修复循环（Task 9 两轮、Task 10 一轮、终审条件一轮），全部闭环 Approved。

## 红线核对

- [x] 业务零侵入：src/ 改动仅 citation.py（注册表）+ citation_node.py（Score 上报）
- [x] `decision-outcome` 在线结算语义零触碰（git diff 实证）
- [x] 未新建 ADR；未手改主规范库（只经 delta）
- [x] 无断言改弱（历轮审查 diff 级核验）

## 待人工事项（archive 前必须）

1. **人工 ADR**：回测基准指数（默认 000300）、标注集专家来源与规模、hedged 措辞契约语义（当前按点值+容差）。
2. **双人背对背标注**替换/扩充 synthetic 种子集（30-50 份历史报告 × 20-30 claim），上报 κ；随 bad case 滚动补库。
3. **真实跑批**（消耗 LLM token，人工触发）：消融 `uv run python -m evals.ablation --tickers ...`；回测 `uv run python -m evals.backtest.run_backtest --codes ...`；对比 `uv run python -m evals.compare <a.json> <b.json>`。
4. 回测 Sharpe>3 时须附 sanity note（`--sanity-note`），否则批次自动标记 invalid。

## Follow-up（终审 triage，建议 issue 化，不阻塞合并）

- 回测系统/基线收益序列的配对对齐为 min 长度截齐（已披露 ci_truncation），改进为同标的持有期窗口对齐
- 消融 analysts 变体不适用的 judge 维度在报告中静默跳过，补显式披露
- unverifiable_monitor CLI Langfuse 不可达时裸 traceback（建议入口 try/except）
- compare.py 显著退步分支无测试；指标集合不对称静默丢弃
- stats.block_bootstrap_stat 对 block_size<=0 无校验
- 其余单任务 deferred minor 见 .superpowers/sdd/progress.md（会话内 triage 记录）
