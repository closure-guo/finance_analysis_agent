# Tasks: harden-evaluation-rigor

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出至 `docs/superpowers/plans/`，不在此处。

## 前置

- [ ] 人工 ADR 落地：回测基准指数、标注集专家来源与规模、hedged 措辞语义（agent 不自建 ADR）
- [ ] 确认与 `decision-outcome-tracking` 的边界：本 delta 只做离线回放，不动 `decision_log` 在线结算语义

## 验收项

### citation-verification

- [ ] `_COMPUTATIONAL_RECALC` 注册表覆盖 `metrics/` 全部纯函数（偿债/盈利/运营/现金流/杜邦/技术/风控），每个根键有重算 fixture 测试
- [ ] 未注册根键的计算型 claim 判 UNVERIFIABLE，且计数为覆盖缺口指标
- [ ] 新增 Score `citation_unverifiable_ratio` 上报 Langfuse，关联 trace_id
- [ ] 既有容差语义（绝对 0.01 / 相对 0.5%）与三态裁决不回归

### evaluation

- [ ] 断言级校验基准集：30-50 份历史报告 × 每份 20-30 条 claim，双人标注 + 仲裁，报告 κ 系数；随 bad case 滚动补库
- [ ] 校验器准度测量脚本：对基准集输出 P/R/F1，含 ±5% 擦边对抗子集与 hedged 措辞子集的分项召回
- [ ] 准度门禁：整体 F1 ≥ 0.90 方可宣称校验结果可信；擦边子集召回单独报告，不设硬门禁但须显式披露
- [ ] run_experiment 对比报告强制配对 bootstrap（B=10,000）95% CI；CI 含 0 时结论只能写"无显著差异"
- [ ] 数据对齐消融：三变体（单分析师直出 / +Bull-Bear / 完整 5 层）× 10 标的 × 3 次重复，接收相同 state 快照；产出各变体 citation_pass 率与 judge 分数的 CI 对比报告

### decision-backtest

- [ ] 离线回放器：固定 prompt/模型版本，输入截断至决策日前（含财报披露滞后近似），数据快照时点可审计
- [ ] 绩效四指标 CR/ARR/Sharpe/MDD，基线 Buy-and-Hold + MACD/KDJ/RSI（复用 `metrics/technical.py`）
- [ ] 分层抽样：≥3 种市场状态（含至少一段下跌市）× 每段 ≥10 股
- [ ] 统计显著性：block bootstrap（B≥1,000，块长 20 交易日）报告 Sharpe CI；附块长敏感性说明
- [ ] Sharpe > 3 的批次强制附 sanity check 说明，否则结果标记无效
- [ ] 决策一致性：同标的 n=3 重复运行，报告方向一致率
- [ ] 结算语义复用 `decision-outcome` 的 A 股异常规则（涨跌停/停牌/复权），不重复造轮子

### 通用

- [ ] `uv run pytest` 全过、`uv run ruff check` 无错误、`uv run mypy` 无错误
- [ ] 评估设施全部位于 `evals/`，业务代码零侵入（注册表扩展除外）
