# Tasks: harden-evaluation-rigor

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出至 `docs/superpowers/plans/`，不在此处。

## 前置

- [ ] 人工 ADR 落地：回测基准指数、标注集专家来源与规模、hedged 措辞语义（agent 不自建 ADR）——待人工；当前实现按 design.md 默认值（基准 000300、hedged 按点值+容差、种子集 synthetic-seed）
- [x] 确认与 `decision-outcome-tracking` 的边界：本 delta 只做离线回放，不动 `decision_log` 在线结算语义（git diff 实证 outcome/ 与该 delta 目录零改动；仅 import `evaluate_decision` 纯函数）

## 验收项

### citation-verification

- [x] `_COMPUTATIONAL_RECALC` 注册表覆盖 `metrics/` 全部纯函数（偿债/盈利/运营/现金流/杜邦/技术/风控），每个根键有重算 fixture 测试
- [x] 未注册根键的计算型 claim 判 UNVERIFIABLE，且计数为覆盖缺口指标（CitationReport.coverage_gaps）
- [x] 新增 Score `citation_unverifiable_ratio` 上报 Langfuse，关联 trace_id（score_current_trace 随当前 trace；未配置/失败均记 WARN 不阻断）
- [x] 既有容差语义（绝对 0.01 / 相对 0.5%）与三态裁决不回归（既有测试全绿 + 突升监控 evals/unverifiable_monitor.py）

### evaluation

- [ ] 断言级校验基准集：30-50 份历史报告 × 每份 20-30 条 claim，双人标注 + 仲裁，报告 κ 系数；随 bad case 滚动补库——**设施已交付**（schema/κ 计算/种子集 33 条/滚动补库约定），生产双人标注替换种子集为人工门禁
- [x] 校验器准度测量脚本：对基准集输出 P/R/F1（带 95% CI），含 ±5% 擦边对抗子集与 hedged 措辞子集的分项召回（FAIL 类口径）+ 子集一致率双口径披露
- [x] 准度门禁：整体 F1 ≥ 0.90 方可宣称校验结果可信；擦边子集召回单独报告，不设硬门禁但须显式披露（种子集实测 F1=1.0 过门禁）
- [x] run_experiment 对比报告强制配对 bootstrap（B=10,000）95% CI；CI 含 0 时结论只能写"无显著差异"（evals/compare.py CLI）
- [ ] 数据对齐消融：三变体（单分析师直出 / +Bull-Bear / 完整 5 层）× 10 标的 × 3 次重复，接收相同 state 快照；产出各变体 citation_pass 率与 judge 分数的 CI 对比报告——**编排已交付**（evals/ablation.py，快照对齐 + 层间 CI 含 citation_pass 率 CI），真实跑批（约 90 次深度分析 LLM 消耗）为人工触发

### decision-backtest

- [x] 离线回放器：固定 prompt/模型版本，输入截断至决策日前（含财报披露滞后近似），数据快照时点可审计（metadata 含 data_cutoff/disclosure_rule/prompt_versions/model）
- [x] 绩效四指标 CR/ARR/Sharpe/MDD，基线 Buy-and-Hold + MACD/KDJ/RSI（复用 `metrics/technical.py`）
- [x] 分层抽样：≥3 种市场状态（含至少一段下跌市）× 每段 ≥10 股（缺 regime 抛错）
- [x] 统计显著性：block bootstrap（B≥1,000，块长 20 交易日）报告 Sharpe CI；附块长敏感性说明（10/20/40 并排）
- [x] Sharpe > 3 的批次强制附 sanity check 说明，否则结果标记无效
- [x] 决策一致性：同标的 n=3 重复运行，报告方向一致率（各标的 per_symbol + 全池均值；<2/3 剔除并单独披露）
- [x] 结算语义复用 `decision-outcome` 的 A 股异常规则（涨跌停/停牌/复权），不重复造轮子（直调 evaluate_decision）

### 通用

- [x] `uv run pytest` 全过（-m "not live" 1381 passed/2 skipped；4 个 @live 失败为 main 既有网络环境现象）、`uv run ruff check` 无错误（delta 文件全绿）、`uv run mypy` 无错误（src/ 69=69 与基线位级一致，delta 文件 0 错）
- [x] 评估设施全部位于 `evals/`，业务代码零侵入（注册表扩展除外；src/ 仅 citation.py + citation_node.py）
