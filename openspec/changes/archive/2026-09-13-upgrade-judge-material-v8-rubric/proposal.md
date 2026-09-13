## Why

round8 基线重建轮 + 维护者代裁（docs/evals/2026-09-13-round8-维护者代裁报告.md）暴露出 judge 输入与 rubric 的两类残留缺陷：① consistency / decision_grounding 的 judge 材料缺【Trader 方案】节，Trader 交易方案被风险辩论（Risk Judge 裁决）静默推翻时 judge 无法核对；debate 材料只堆原始发言，judge 需自行推断交锋收敛情况，覆盖率形式指标提示常被忽略。② rubric v7 执行层面两处偏差——debate 5 分档把关时松时紧（美的/宁德两行含纯定性论点仍给满分），dg 归属层对「同一评判在多来源出现」判定偏机械（比亚迪 ref7 归 debate_bear 被误判错安，扣分无据）。这些已登记 metrics.md 待决策，是 v8 校准轮的输入。

## What Changes

- **judge 材料升级（consistency）**：材料新增【Trader 方案】节（TradeDecision 的 action/position_size/价位/触发条件结构化渲染），使 consistency judge 可核对「Risk Judge 裁决是否静默推翻 Trader 方案」链路。
- **judge 材料升级（debate_quality）**：多空辩论记录材料新增骨架行——交锋覆盖统计（N/M 论点被回应）+ 收敛信号摘要（双方第二轮是否出现立场靠拢/共识点/核心分歧保留项），原始发言保留在骨架行之后。
- **rubric v8（consistency）**：rubric 版本 3→4，核对清单追加「Risk Judge 裁决相对 Trader 方案是否有未说明的方向/参数推翻」，配合新增的【Trader 方案】材料节。
- **rubric v8（decision_grounding）**：rubric 版本 7→8，追加归属判例「同一评判在多个来源（如 debate_bear 与 research_manager）均有原话时，引用任一真实来源即合法，不因未选『最早』或『主要』来源扣分」。
- **rubric v8（debate_quality）**：rubric 版本 3→4，5 分档追加判例「论点列表（R1/R2 标头）中任一条为纯定性表述（无数据/事实支撑的断言，含『历史上……』类无样本论据）即降 4，即使该回应其余部分数据密集」。
- **实验排期约束**：材料升级与 rubric v8 均改变 judge 行为，round9 实验预登记 SHALL 按混合变量轮登记（同 round8 先例，按桶归因，不把差异单一归因）。
- prompt 部署纪律：rubric 非部署 prompt，不受 deploy_prompts 门禁约束；材料渲染代码变更走单测。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `evaluation`: 「LLM-as-Judge 评估器与 rubric 标准」要求更新——consistency/debate_quality 的 judge 输入材料构成变化（Trader 方案节、辩论收敛骨架行）；「decision_grounding 评估」「Judge 校准门禁」随 rubric v8 版本递增与归属判例更新重校准。

## Impact

- `evals/judges.py`：RUBRIC_VERSIONS 两处递增 + 两条 rubric 判例追加。
- `evals/`（材料构建函数，具体文件 design 定）：consistency/debate 材料组装新增 Trader 方案节与骨架行；state 中 trade_decision 已可用，无新数据依赖。
- `tests/evals/test_judges.py`：版本断言与 v8 锚点更新。
- 实验流程：round9 预登记（metrics.md §2）、runs.jsonl、校准对照 round8 代裁基线。
- 不影响后端 5 层流水线、前端、citation 链路；无 schema/breaking 变更。
