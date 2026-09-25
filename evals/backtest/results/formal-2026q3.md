# 回测报告：formal-2026q3

**status**: active
**日期**: 2026-09-25T23:49:19
**批次类型**: formal
**预登记**: D:\WorkSpace\finance_analysis_agent\.worktrees\formal-batch\evals\ablation\preregister\2026-09-23-outcome-forward-and-backtest.md（valid）

## 1. 干净窗口判定

- 判定：通过
- 理由：全部 30 个决策日距 as_of(2026-09-25) ≥ 20 个交易日（最少 360）

## 2. 泄漏探针

- 状态：可测（低于阈值）
- 抽样标的数 probe_n：30；题目构成 questions_per_ticker：3（方向 / 幅度桶 / 事件各一，主指标为方向题）
- 方向命中率 direction_hit_rate：60%（阈值 threshold：60%）
- 幅度桶命中率 magnitude_hit_rate：20%；事件题命中率 event_hit_rate：100%（辅证层，不计入主指标）
- 未知占比 unknown_ratio：30%
- 探针窗口 probe_window：2025-01-27, 2025-03-31, 2025-04-07（批内 distinct 决策日各探一次，取最差态汇总；仅覆盖该窗口）

逐窗口读数（聚合规则：不可测 > 超阈 > 可测；不可测态三率一并置空）：

| 窗口 | 状态 | direction_hit_rate | probe_n | unknown_ratio |
|---|---|---|---|---|
| 2025-01-27 | 可测（低于阈值） | 60% | 10 | 26.7% |
| 2025-03-31 | 可测（低于阈值） | 30% | 10 | 30% |
| 2025-04-07 | 可测（低于阈值） | 40% | 10 | 23.3% |

## 3. regime 覆盖

- covered：bear, bull, sideways
- 是否受限：全覆盖

## 4. 绩效表

| 策略 | CR | ARR | Sharpe | MDD |
|---|---|---|---|---|
| system | -0.0941 | -0.4636 | -1.5145 | 0.1439 |
| buy_hold | 0.0864 | 0.6855 | 1.6007 | 0.1065 |
| macd | -0.1089 | -0.5164 | -3.9663 | 0.1089 |
| kdj | 0.0157 | 0.1031 | 0.4783 | 0.0838 |
| rsi | 0.0878 | 0.6996 | 1.9600 | 0.0717 |

（最优基线 best_baseline：rsi）

## 5. 结论

无显著差异

## 6. 口径说明

- 入场/结算语义：结算语义与生产 track-record 判定同源（horizon/超额/±2% 带；入场价由行情派生）
- 日收益口径：单笔结算收益摊到持有期逐日；基线为 T-1 信号 T 生效的逐日仓位收益
- 基准：BENCHMARK_CODE 默认 000300（沿 decision-outcome 默认，待 ADR 确认）
- 复权口径（hfq）：结算/回测区间收益走后复权（hfq，SETTLEMENT_ADJUST，Δ4 Task 1 统一）；指数无复权概念，基准取原始点位
- 非可执行决策排除：system 收益仅计 buy/sell 决策（long/short）；hold/watch（neutral，回避语义）整条排除、不计方向化收益（§1.9② 主结论仅基于可执行决策），被排除的已一致标的数见 excluded_non_executable
- 复权：结算/回测区间收益走后复权（hfq），非可执行决策（hold/watch）整条排除。
