# Backlog 索引（2026-09-04 盘点立项）

来源：「完善 agent 功能与可观测性」总盘点后的剩余事项。全部为提案级脚手架（proposal + 最小 delta spec + tasks 骨架），实施前需按 §3 管线补全设计。

## 历史战绩（依赖序：stage-b → stage-c）

| Delta | 内容 | 前置 |
|---|---|---|
| `add-track-record-stage-b` | 盯市/净值曲线/风险收益指标引擎（年化/回撤/夏普/风险分），P4 收益风险成对 | 阶段 A 已完成 ✅ |
| `add-track-record-stage-c` | 校准分桶+Brier、四维切片、观点详情页、版本分段（P6）、完整性校验+审计 | stage-b |

> 注：原计划的 `add-track-record-versioning` 已并入 stage-c（版本分段属 P6 语义，单独拆开会重复造 agents 表）。

## 决策质量

| Delta | 内容 | 前置 |
|---|---|---|
| `calibrate-fm-approval` | FM 永不批准问题：取证 + prompt 校准 + 决策分布双向门禁（防永不批准/防无脑批准） | 无；建议与 judge-human-calibration 共用人工抽检 |

## 评估体系补强（均落在 agent-evaluation-suite 能力上）

| Delta | 内容 | 前置 |
|---|---|---|
| `add-judge-human-calibration` | judge 与人工标注对齐（Spearman/MAE/方向一致率）+ 校准回路 | 人工标注资源 |
| `add-toolcall-evaluation` | quick 模式工具调用维度（合法集合断言/循环检测/失败恢复） | trace 归因已完成 ✅ |
| `add-hallucination-rate-metric` | 事实性 claim 抽取 + 证据校验 + 幻觉率门禁 | 可与 toolcall 共用证据源 |
| `add-latency-cost-regression` | 时延/token/成本基线与回归门禁 + 趋势告警 | 无（纯评测侧增量） |
| `enable-hosted-evaluator` | Langfuse hosted evaluator 在线评分 + 口径对齐 + 告警 | 需先确认自托管版本能力（tasks 0.1） |

## 并行冲突提示

- 5 个评估类 delta 都 MODIFIED `agent-evaluation-suite`：同时只做一条，sync 后再开下一条，避免 delta 互相覆盖。
- 评估类 delta 共用「人工抽检批次」，建议 calibrate-fm-approval 与 add-judge-human-calibration 结对实施。
