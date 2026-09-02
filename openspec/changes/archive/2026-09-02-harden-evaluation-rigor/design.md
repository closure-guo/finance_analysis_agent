# Design: harden-evaluation-rigor

## Context

本 delta 把两篇论文的评估方法论落地为本系统的契约：

| 来源 | 移植内容 | 落点 |
|------|---------|------|
| FinGround 检索对齐评估 | 控制变量消融：所有变体接收相同输入，隔离被测组件贡献 | `evaluation` 数据对齐消融 |
| FinGround FinHalu 标注集 | 断言级人工标注集 + 校验器自身 P/R 测量 | `evaluation` 校验基准集 |
| FinGround 错误分析 | ±5% 擦边对抗子集、hedged 措辞子集 | `evaluation` 准度门禁 |
| FinGround 公式模板库 | 计算型 claim 全部走确定性重算（本系统用纯函数注册表实现，优于 LLM 重算） | `citation-verification` |
| TradingAgents 指标体系 | CR / ARR / Sharpe / MDD + 规则基线对比 | `decision-backtest` |
| TradingAgents 反面教训 | 小样本、单 regime、无显著性检验、夏普异常未解释 | `decision-backtest` 抽样与统计契约 |

## Goals / Non-Goals

### Goals

- 校验器从"裁判无证上岗"变为"自身准度可测量、有门禁"
- 实验对比从"点估计拍脑袋"变为"置信区间说话"
- 决策评估从"事后等结果"（在线追踪）补全为"历史可回放"（离线回测）
- 5 层架构的 token 开销有归因依据

### Non-Goals

- 不引入 LLM 重生成修复回路（FinGround Stage 3）：本系统校验是确定性的，FAIL 断言的处置（flag-only / 重试环）属另一 delta 范畴
- 不改既有容差语义（绝对 0.01 / 相对 0.5%）与三态裁决
- 不建在线实盘跟踪（已由 `decision-outcome-tracking` 覆盖）
- 不做跨 LLM 生成器迁移评估（当前后端单一，留作后续）

## Decisions

### D1: 离线回测独立为 `decision-backtest`，不并入 `decision-outcome`

`decision-outcome` 是"产出即落库、日批结算"的在线闭环，语义是**向前看**；离线回测是"拿历史数据重演管线"，语义是**向后重演**，且需要 prompt/模型版本固定、可批量重复。两者数据源、触发时机、幂等性要求均不同，合并会污染 `decision-outcome` 的在线契约。

### D2: 计算型校验坚持确定性重算，不引入公式模板 LLM 识别

FinGround 用 47 个公式模板 + LLM 识别隐含公式，是因为它的证据是**非结构化 SEC 文档**。本系统的 ground truth 是 `state` 中的结构化数据，`metrics/` 纯函数即可从原始报表重算任意指标——注册表路径更确定、零 token、可进 CI，是严格更优解。代价是覆盖率受限于注册表，故用契约强制"全覆盖 + 未注册根键计为覆盖缺口"。

### D3: 统计方法选型

- **分数对比**（judge 分数、citation_pass 率）：配对 bootstrap（B=10,000，对齐 FinGround 规格），按 dataset item 重采样，报告 95% CI；CI 含 0 则结论为"无显著差异"，禁止用语义化措辞包装点估计差异。
- **回测 Sharpe / 收益**：block bootstrap（B≥1,000），按交易日块重采样以保留时序相关性；块长默认 20 交易日，契约要求附块长敏感性说明。
- **为何不用置换检验**：回测场景是"策略 vs 基线"两条相关时序，配对块 bootstrap 更自然；FinGround 的置换检验用于独立样本分数对比，本 delta 不照搬。

### D4: 消融变体的输入对齐实现

三个变体（单分析师直出 / +Bull-Bear 辩论 / 完整 5 层）接收**完全相同**的 `fetch_data` + `compute_metrics` 输出。state 已是结构化 TypedDict，通过对同一 trace 的 state 快照重放实现对齐，无需修改业务节点。这复刻 FinGround"所有系统接收相同检索结果"的控制条件。

### D5: 前视偏差防控

回测回放时，管线数据输入 SHALL 截断至决策日之前的可得数据（含财报披露滞后：A 股季报/年报按法定披露截止日近似）。契约层面要求回测器提供"数据快照时点"字段并可审计，而非信任各 fetch 函数自觉。

## Risks / Trade-offs

- **标注集规模**（30-50 份报告 × 20-30 条 claim）统计功效有限 → 契约要求报告置信区间，且标注集随 bad case 滚动补库，不一劳永逸。
- **LLM 不确定性** → 决策一致性要求 n=3 重复；消融实验每变体每标的跑 3 次取中位。
- **回测过拟合历史** → 契约强制分层市场状态（至少含一段下跌市），禁止只在单边行情上汇报。
- **夏普异常值** → TradingAgents 教训：契约要求 Sharpe > 3 时必须附 sanity check 说明（样本期、回撤、换手率），否则结果无效。
- **成本**：回测回放消耗 LLM token → 分层抽样控制规模（3 regime × 10 股 × 3 次 ≈ 90 次深度分析），允许先用 `deepseek-chat` 降级跑批筛查。

## Migration Plan

纯新增评估设施，无业务行为变更。既有 `citation_pass` 等 Score 语义不变。上线顺序：

1. 注册表扩展 + UNVERIFIABLE 监控（零风险，先行）
2. 校验基准集标注（人工密集，可与 1 并行）
3. 回测器 + 分层抽样跑批
4. 消融实验
5. 统计显著性接入 run_experiment 报告格式

## Open Questions

- 回测基准：沪深 300 之外是否加中证 500 / 创业板指（标的池跨板块时需要）？→ 待人工确认，默认沿用 `decision-outcome-tracking` 的 000300。
- 标注集的专家来源：团队内部 2 人 + 仲裁，还是外部标注？→ 影响 κ 系数的解释力。
- hedged 措辞（"约 45%"）的契约语义：按区间解析还是统一按点值 + 容差？→ 本 delta 暂按后者，待基准集测量出实际假阳率后再议。
