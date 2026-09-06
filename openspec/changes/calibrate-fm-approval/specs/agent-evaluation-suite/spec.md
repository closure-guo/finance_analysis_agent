# agent-evaluation-suite Specification Delta

## ADDED Requirements

### Requirement: RM 决策分布追踪

评估链路 SHALL 从 Langfuse trace 聚合基金经理节点（fund_manager）的决策分布（approve/return/reject）并输出报告，含按时间分桶趋势。分布 SHALL 不设硬性占比下限（对高风险标的的否决是职责所需），仅 nightly 记录供防漂移比对。

#### Scenario: 分布统计

- **WHEN** nightly 评估运行且存在 fund_manager trace
- **THEN** 报告输出 approve/return/reject 计数与占比、按日分桶
- **AND** 分布变化仅作为趋势记录，不直接判决失败

#### Scenario: 无 trace

- **GIVEN** 无任何 fund_manager trace
- **WHEN** 运行分布统计
- **THEN** SHALL 返回空分布并在报告中标注「样本不足」，不报错

### Requirement: 风控否决召回门禁

对回撤或波动率超过配置阈值的对抗样本，FM SHALL 必须否决（approve 即门禁失败）；随机真实样本的否决率 SHALL 同步上报。本门禁防「无脑批准」反向漂移，与「不设占比下限」互为约束。

#### Scenario: 高风险样本必须否决

- **GIVEN** 对抗样本的风控指标（max_drawdown / volatility）超过阈值
- **WHEN** FM 输出 approve
- **THEN** 门禁失败并输出该样本

#### Scenario: 正常样本上报否决率

- **WHEN** 随机真实样本集上 FM 输出分布已知
- **THEN** 报告上报样本级否决率，不设判决阈值

### Requirement: 否决理由完整门禁

FM 的 approve/return/reject 决策 SHALL 附带 reasoning；理由缺失或为空 SHALL 判门禁失败，防止「退回后未改进即拒绝」等无理由退化。

#### Scenario: 缺理由拒绝

- **WHEN** FM 输出 decision 但 reasoning 缺失或空白
- **THEN** 门禁失败并输出对应 trace/样本

### Requirement: return 回路反馈

系统 SHALL 在 FM 返回 `return` 后路由回 trader 重跑时，把 `fund_manager_decision_reasoning` 并入 trader 的 LLM context，使 Trader 能针对退回理由改进方案；最终报告 SHALL 反映重跑后的方案而非原始方案。

#### Scenario: 退回后重跑携带反馈

- **GIVEN** FM 首次评估产出 return 且带 reasoning
- **WHEN** 管线路由回 trader 节点重跑
- **THEN** trader 的 LLM context 包含该退回理由

#### Scenario: 无退回时不注入

- **GIVEN** FM 首次评估产出 approve 或 reject
- **WHEN** trader 节点运行
- **THEN** context 不包含基金经理退回意见段落