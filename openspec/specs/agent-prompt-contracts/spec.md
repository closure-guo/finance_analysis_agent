# Agent Prompt Contracts

## Purpose

定义各角色 LLM 提示词模板（`src/finance_agent/prompts/*.md` 及散落硬编码 system prompt）的行为契约：反幻觉硬规则、对抗性辩论指令、决策语义契约、摘要数据接地，以及提示词可测试性与股票解析单一实现。提示词是行为契约的一部分——本轮从 TradingAgents / ai-hedge-fund 对标总结出缺口后沉淀为硬性要求，防止 LLM 输出编造数据、辩论各说各话、置信度无语义。

## Requirements

### Requirement: 分析师反幻觉硬规则

每个分析师提示词（fundamental、macro、technical、sentiment）MUST 包含反幻觉硬规则段，要求 LLM 仅基于输入数据推理，以数据最新日期为"现在"，不得编造数据；各分析师方法论 MUST 体现周期感知与数据时效意识。

#### Scenario: 分析师输出基于输入数据

- **WHEN** 加载任一分析师提示词模板（fundamental_analyst / macro_analyst / technical_analyst / sentiment_analyst）
- **THEN** 模板中包含"仅使用提供的数据"约束
- **AND** 模板中包含"不得编造数字/数据"约束
- **AND** 模板中包含"以数据最新日期为现在，不使用该日期之后的知识"约束

#### Scenario: 数据不足时分析师明示降级

- **WHEN** 分析师收到的输入数据缺失或不足以支持某项分析
- **THEN** 分析师 MUST 在报告中显式标注数据不足
- **AND** MUST NOT 编造缺失数据填补分析

#### Scenario: 分析师方法论周期感知

- **WHEN** 加载 fundamental_analyst 提示词
- **THEN** 模板中 ROE/负债率等阈值表述为"同业相对 + 周期调整"语义（如"与同业中位数对比并按当前利率/通胀环境调整"），而非孤立绝对值
- **AND** 加载 technical_analyst 提示词时模板包含"强趋势中 RSI/KDJ 可能钝化、以 MA 趋势为主"类提示
- **AND** 加载 macro_analyst 提示词时模板包含"M1/M2 剪刀差判读"与"数据滞后时标注时效并降级结论"类提示

### Requirement: 辩论者对抗性指令

bull_debater、bear_debater、risk_debater 提示词 MUST 包含对抗性辩论指令，要求逐条引用对手论点并反驳，而非仅复述自身报告。

#### Scenario: 辩论者反驳对手论点

- **WHEN** 加载 bull_debater / bear_debater 提示词
- **THEN** 模板中包含"针对对方上一轮论点逐条反驳"类指令
- **AND** 模板中包含"先引用对手论点（原文或要点）再给出反论"类指令

#### Scenario: 风险辩论者回应其他方位

- **WHEN** 加载 risk_debater 提示词
- **THEN** 模板中包含要求回应其它风险方位论点（激进/保守/中性）的指令

### Requirement: Trader 决策语义契约

trader 提示词 MUST 定义 action 各档位的语义与 position_size 档位含义，并为 confidence 提供分档锚点。

#### Scenario: Trader 输出带语义的决策

- **WHEN** 加载 trader 提示词
- **THEN** 模板中包含 action（buy/sell/hold/watch）各档位的行为语义描述
- **AND** 模板中包含 position_size 档位定义（如 light/moderate/heavy 对应仓位区间）
- **AND** 模板中包含 confidence 分档语义（如 0.7+ 高置信、0.4-0.7 中等、<0.4 低置信）

### Requirement: 风控与审批评级量表

risk_judge、fund_manager 提示词 MUST 提供评级/决策选项的语义说明，指导在证据均衡或不足时如何取舍。

#### Scenario: Risk Judge 输出评级量表决策

- **WHEN** 加载 risk_judge 提示词
- **THEN** 模板中包含 buy/sell/hold/watch 的语义与取舍指导（如证据均衡时倾向 hold/watch）

#### Scenario: Fund Manager 审批决策语义

- **WHEN** 加载 fund_manager 提示词
- **THEN** 模板中包含 approve/reject/return 三种决策的适用语义说明

### Requirement: Research Manager 评级表态

research_manager 提示词 MUST 要求 LLM 给出明确的看多/看空/中性倾向与依据，而非仅复述多空双方观点；证据均衡时必须显式说明取舍理由。

#### Scenario: Research Manager 输出明确倾向

- **WHEN** 加载 research_manager 提示词
- **THEN** 模板中包含"必须给出明确评级倾向（看多/看空/中性）"类指令
- **AND** 模板中包含"证据均衡时须说明取舍理由，而非回避表态"类指令
- **AND** 模板中包含"基于辩论历史中的具体论据，而非泛泛而谈"类指令

### Requirement: 摘要仅基于输入材料

报告摘要（report.py focus summary）与 deep_mode 对话摘要 MUST 仅基于管线上游材料/工具输出组织内容，不得引入材料外数值或知识。

#### Scenario: 报告摘要基于上游材料

- **WHEN** 加载 report.py 摘要 prompt 或 deep_mode 提示词
- **THEN** 模板中包含"仅使用所提供材料中的数据"约束
- **AND** 模板中包含"不得引入材料外/工具输出外的数值"约束

#### Scenario: 摘要不得引用过期宏观数据作为最新值

- **WHEN** 管线上游宏观数据（PMI/CPI）最新日期与当前日期相差超过 3 个月
- **THEN** 摘要/分析 MUST 标注该指标数据时效滞后，不得将其表述为当前最新状态
- **AND** 相关结论 MUST 降低置信度或明示基于滞后数据

### Requirement: 股票解析收敛单一实现

股票名称/代码的 LLM 解析 MUST 收敛到 react_agent.py 的单一实现；nlp.py 冗余解析与未引用的 REACT_SYSTEM_PROMPT 死代码 MUST 被移除。

#### Scenario: 移除冗余解析后单一入口

- **WHEN** 执行股票解析收敛任务
- **THEN** 股票解析 LLM 提示词仅存在于 react_agent.py 一处（契约测试断言通过）
- **AND** nlp.py 中的冗余 LLM 解析函数已移除，且无生产代码引用（断言通过）
- **AND** react_agent.py 中未被引用的 REACT_SYSTEM_PROMPT 常量已移除（断言通过）

### Requirement: 提示词契约可测试性

提示词模板改动 MUST 附带可执行的契约测试，验证关键指令段存在，防止后续编辑漂移。

#### Scenario: 契约测试断言关键指令存在

- **WHEN** 运行提示词契约测试套件
- **THEN** 每个分析师提示词包含反幻觉硬规则段（断言通过）
- **AND** 每个辩论者提示词包含对抗性指令（断言通过）
- **AND** trader / risk_judge / fund_manager 提示词包含决策语义段（断言通过）
- **AND** research_manager 提示词包含评级表态指令（断言通过）