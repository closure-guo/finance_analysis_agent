# Proposal: calibrate-fm-approval

## Why

原假设「基金经理从不 approve、只有 reject」经取证证伪。Langfuse 153 条 `fund_manager` trace 中 approve 81（53%）、return 44（29%）、reject 24（16%）；09-03 当天 approve 19/44（43%）。FM 批准行为正常，**历史战绩为空是此前落库缺陷（已单独修复）造成的错觉，不是 FM 不批准**。

用户观察到的「连续只见 reject」窗口 = 同一高风险标的（力鼎光电，真实计算回撤 41.2%/波动率 75.6%）被反复重跑：`return → trader 重跑 → FM 再评` 回路中 **trader 重跑未携带 FM 的退回理由**（`_build_trader_context` 不读 `fund_manager_decision_reasoning`），产出同方案 → FM 依风控职责再拒 → 以 reject 收场（012:31–13:15 的 11 连非 approve 全是这一标的）。

结论：FM 否决高风险标的（回撤 41%/波动 76%）是职责所需，**不得用「approve 占比下限」放松风控**。可修的真实缺陷是 return 回路反馈断裂 + 评估侧缺少 FM 决策质量守门。

## What Changes

- **return 回路修复**：trader 节点在 return 重跑时把 `fund_manager_decision_reasoning` 并入 LLM context，使 Trader 能按 FM 要求补充论据（风险缓释/仓位控制/止损安排），FM 再评时面对改进后的方案
- **评估接入**：
  - `fm_decision_distribution` 指标：从 Langfuse trace 聚合 approve/return/reject 分布与趋势，nightly 报告（不设占比下限，仅记录波动防漂移）
  - 风控否决召回门禁：对回撤/波动超阈值的对抗样本，FM 必须否决（approve 即失败）——防「无脑批准」反向漂移
  - 否决理由完整门禁：approve/return/reject 必须附带 reasoning，缺失/为空即失败（防无理由拒绝的退化）
- **prompt 不改**：取证证明 FM prompt 行为健康，改动反而引入生产风险；如需再校准，走既有 deploy 管线另立条目

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增 FM 决策分布追踪 + 风控否决召回门禁 + 否决理由完整门禁

## Impact

- 代码：仅 `src/finance_agent/nodes/trader.py`（context 注入 + 对应单测）；graph/routing 不变（return 回路已存在）
- 数据：无新表
- 评估：`evals/fm_decision/` 模块（Langfuse 拉取 + fixtures 离线断言）+ 对抗样本集
- 前端：无
- 前置：无