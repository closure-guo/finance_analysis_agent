# Proposal: calibrate-fm-approval

## Why

排查确认：基金经理（FM）节点历史上从未产出 `approve`，100% `reject`/`modify`。这意味着五层流水线的最后一关实际退化为「否决器」——approve 路径代码、前端批准态展示、战绩体系的「批准买入」语义全部从未被真实触发。根因候选：prompt 过度风险厌恶（v2 合并后需复核）、输入上下文缺少「必须给出可执行结论」的约束、或 approve 的判定门槛表述模糊。

## What Changes

- 取证：基于 Langfuse trace + 战绩库统计 FM 决策分布，定位 prompt 层 vs 数据层根因（只读分析，先落结论）
- prompt 校准：在保留风控职责的前提下，明确三档决策的判定标准与「不得无限期回避决策」约束；给出 approve/modify/reject 的示例锚点
- 校准指标：`fm_decision_distribution` 进入评估体系（approve/modify/reject 占比 + 与人工抽检的一致率），防止「校准成无脑 approve」的反向漂移
- 回归门禁：评测集新增 FM 决策分布断言（如 approve+modify 占比下限），纳入 nightly @live

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增 FM 决策分布指标与门禁断言
- `prompt-deploy-consistency`: FM prompt 变更走既有部署管线（无新规则，仅声明受影响 prompt）

## Impact

- 受影响 prompt：`src/finance_agent/prompts/fund_manager.md`（改后必须 `scripts/deploy_prompts.py` 发布）
- 评估：`evals/` 新增指标与断言；nightly @live 用例
- 前置：无代码结构依赖，但建议与 add-judge-human-calibration 共用人工抽检样本
- 风险：校准过度会使 FM 形同虚设——指标设计必须双向约束（approve 率上限 + 风控否决召回率下限）
