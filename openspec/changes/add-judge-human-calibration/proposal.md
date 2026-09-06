# Proposal: add-judge-human-calibration

## Why

LLM-as-judge 评分目前是「自评自判」——judge 本身的打分从未与人工标注对齐过。judge 若系统性偏松/偏紧，所有下游门禁（防退化）与消融结论（批次 1-4）都建立在一个未校准的裁判上。批次 3/4 已引入维度适用性与 delta 归档，但「裁判可信度」这一环仍缺。

## What Changes

- 人工标注工具：`tests/scripts/` 新增标注脚本，从 Langfuse 抽样 trace 导出评判表（维度 × 人工 1-5 分），支持多人/多轮标注与仲裁
- 一致性指标：judge 分 vs 人工分的 Spearman 相关、MAE、方向一致率；输出校准报告至 `reports/`
- 校准回路：一致性低于阈值时触发 judge prompt 修订流程（走 prompt-deploy-consistency 管线）；校准结论归档至 `docs/evals/`
- 周期性：纳入 nightly 或按版本触发（judge prompt 变更后必跑）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增 judge-人工一致性校准回路（标注工具、一致性指标、校准触发条件）

## Impact

- 新脚本：`tests/scripts/judge_calibration_*.py`；样本集落 `tests/fixtures/`
- 依赖：Langfuse trace 导出（既有）；与 calibrate-fm-approval 可共用人工抽检批次
- 成本：人工标注是人力活，需约定抽样规模（建议每轮 ≥30 条、覆盖快慢双模式）
