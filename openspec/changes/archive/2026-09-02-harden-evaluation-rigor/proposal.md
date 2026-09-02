# Proposal: harden-evaluation-rigor

## Why

系统的评估能力目前只有"单点打分"，缺"测量学"：

1. **校验器自身无考卷** —— `citation.py` 判 Agent 的 claim，但没有任何标注集判它。`_COMPUTATIONAL_RECALC` 仅注册 `dupont_tree` 一个根键，而 `metrics/` 下 29 个纯函数（偿债 5 / 盈利 5 / 运营 4 / 现金流 6 / 杜邦 / 技术 / 风控）均未注册，计算型 claim 大面积落入 UNVERIFIABLE；擦边错误（±5% 内）与 hedged 措辞（"约""可能"）两个 FinGround 实证盲区（召回降至 71.4%、占假阳 52%）从未被测量。
2. **实验对比无显著性** —— `agent-evaluation-suite` 建立了 run_experiment 回归，但对比只看分数点估计；`baseline-v2 r3` 式的回归判断没有置信区间支撑，改 prompt 仍可能"凭手感"。
3. **决策效果无离线回放** —— delta `decision-outcome-tracking` 补齐了"事后向前追踪"，但 prompt/模型变更需要**离线、可重复、即时**的验证手段；TradingAgents 的教训（3 股 × 3 月、夏普 5.6-8.2 无法解释、无显著性检验）必须显式规避。
4. **5 层辩论架构价值未归因** —— Bull/Bear 辩论、风险辩论各贡献多少？与 TradingAgents 一样从未消融。FinGround 的检索对齐评估（retrieval-equalized evaluation）提供了可直接移植的控制变量范式。

参考：FinGround（arXiv:2604.23588）方法论；TradingAgents（arXiv:2412.20138）指标选型与反面教训。

## What Changes

1. **`citation-verification` 扩展** —— 计算型重算注册表覆盖全部 `metrics/` 纯函数；UNVERIFIABLE 占比作为数据层退化的先行指标上报。
2. **`evaluation` 扩展** —— 新增断言级校验基准集（claim-level labeled set）+ 校验器准度门禁（含 ±5% 擦边对抗子集与 hedged 措辞子集）；实验对比强制配对 bootstrap 置信区间；新增数据对齐消融实验协议（三变体同 state 输入，归因辩论层价值）。
3. **新建 `decision-backtest` capability** —— TradeDecision 历史离线回放：分层市场状态抽样、绩效四指标（CR/ARR/Sharpe/MDD）、规则基线对比、block bootstrap 显著性、n=3 重复运行的决策一致性。

## Capabilities

### New Capabilities

- `decision-backtest`: 交易决策的历史离线回放评估 —— 分层抽样回放 + 绩效指标 + 基线对比 + 统计显著性 + 决策一致性。与 `decision-outcome`（在线向前追踪）互补：一个回答"历史重演会怎样"，一个回答"这次建议后来赚没赚"。

### Modified Capabilities

- `citation-verification`: 新增计算型重算覆盖与 UNVERIFIABLE 监控要求。既有容差语义（绝对 0.01 / 相对 0.5%）与三态裁决契约不变。
- `evaluation`: 新增校验基准集、统计显著性、消融实验三类要求。既有 judge / dataset / run_experiment 契约不变。

## Impact

- **新增代码**：`evals/claim_benchmark/`（标注集 + 准度测量）、`evals/backtest/`（回放器 + 指标 + 基线 + bootstrap）、`evals/ablation/`（变体编排）；`citation.py` 重算注册表扩展（纯函数注册，无 LLM）。
- **Langfuse**：新增 Score `citation_unverifiable_ratio`；实验报告格式变更（分数须附带 CI）。
- **协调**：与 `decision-outcome-tracking` 互补不重叠（离线 vs 在线，Score 互不冲突）；与 `agent-evaluation-suite` 的关系是**强化而非替代**（本 delta 给其实验工作流加统计门槛）。
- **依赖**：消融实验依赖 state 结构化输入可复现（既有）；回测依赖 AKShare 历史日 K（既有，`decision-outcome-tracking` 已复用同路径）。
- **架构决策**：回测基准集与持仓语义默认值需人工确认；涉及"评估口径"决策，**建议人工落一条 ADR**（agent 不得新建 ADR）。
- **风险**：中 —— 回测存在前视偏差风险（对策：契约强制时点数据快照语义）；标注集规模小（30-50 份报告）存在过拟合风险（对策：随 bad case 滚动补库）；bootstrap 结果对块长敏感（对策：契约规定块长与敏感性检查）。
