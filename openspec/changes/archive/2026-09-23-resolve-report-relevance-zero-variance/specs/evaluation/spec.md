# Delta for Evaluation

## ADDED Requirements

### Requirement: report_relevance 评估范围与 5 分档判例

report_relevance SHALL 仅对 deep 条目评估：quick 条目 SHALL 跳过 report_relevance 判分（不发起 judge 调用、不产出该维分数），其回归信号由确定性指标（ticker_match / section_coverage / citation 系）承担。deep 条目的 report_relevance rubric SHALL 自 v4 起执行 5 分档锚点判例：query 中可辨识的显式子问题被逐一回答方可给 5，任一子问题被回避或仅泛泛带过即降 4。rubric 版本 SHALL 递增记录于 `RUBRIC_VERSIONS`，并按「Judge 校准门禁」契约重校准（与人工一致性 ≥80%）后方可上线。本变更合入 SHALL 在 `docs/evals/metrics.md` §1.1 更新口径（deep-only）并登记时间线切点：跨切点的 report_relevance 均值不可直接比较。

#### Scenario: quick 条目跳过 judge

- **GIVEN** dataset 含 mode=quick 的条目
- **WHEN** run_experiment 处理该条目
- **THEN** SHALL NOT 对其发起任何 judge 调用，其结果记录 SHALL NOT 含 report_relevance 分数
- **AND** 确定性指标（ticker_match / section_coverage / citation 系）SHALL 照常评估

#### Scenario: deep 子问题回避降档

- **GIVEN** query 为「分析 XX 的估值和分红能力」，报告仅覆盖估值、分红一笔带过
- **WHEN** 运行 report_relevance judge（rubric v4）
- **THEN** judge SHALL 按 5 分档锚点判例降 4（显式子问题未逐一回答）
- **AND** 输出 reason SHALL 指明被回避的子问题

#### Scenario: 重校准后上线

- **WHEN** rubric v3 → v4 变更
- **THEN** SHALL 以校准样本离线重判 v4 并与人工分对照，一致性 ≥80% 后方可合入生产判分路径
- **AND** `RUBRIC_VERSIONS` 的 report_relevance SHALL 递增为 4

#### Scenario: 切点登记

- **WHEN** 本变更合入并首轮实验收口
- **THEN** `docs/evals/metrics.md` 时间线 SHALL 新增切点行（report_relevance 转为 deep-only + rubric v4）
- **AND** 跨切点的 report_relevance 均值 SHALL 标注不可直接比较

## MODIFIED Requirements

### Requirement: 线上托管 Evaluator

第二阶段，系统 SHALL 在 Langfuse 服务端配置线上托管 Evaluator，与线下实验用同一套 rubric 与裁判模型，按采样率（初值 10-20%）对生产 trace 自动评估，结果作为 Monitors 告警信号。judge 评估 SHALL 仅对 deep 模式 trace 生效：quick 模式 trace SHALL NOT 跑任何 judge 维度（report_relevance 已转 deep-only），Monitors 告警 SHALL 以 deep trace 的 judge 分与确定性指标为信号源。

(Previously: 第二阶段，系统 SHALL 在 Langfuse 服务端配置线上托管 Evaluator，与线下实验用同一套 rubric 与裁判模型，按采样率（初值 10-20%）对生产 trace 自动评估，结果作为 Monitors 告警信号。quick 模式无辩论，仅跑 `report_relevance`。)

#### Scenario: 采样评估

- **GIVEN** 线上 deep trace 产生
- **WHEN** 命中采样率
- **THEN** 托管 Evaluator SHALL 按同 rubric 自动跑 Judge
- **AND** Score 附着到该 trace

#### Scenario: 模式过滤

- **GIVEN** trace 的 `mode=quick`
- **THEN** 托管 Evaluator SHALL 跳过全部 judge 维度（report_relevance 为 deep-only），SHALL NOT 为 quick trace 产生 judge Score
- **AND** quick trace 的质量信号 SHALL 来自确定性指标

#### Scenario: 漂移告警

- **WHEN** 某 Judge Score 均值在窗口内骤降
- **THEN** Monitors SHALL 触发告警（webhook）
