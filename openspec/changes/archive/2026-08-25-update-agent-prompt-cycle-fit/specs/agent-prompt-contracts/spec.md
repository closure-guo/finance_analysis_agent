# Delta for Agent Prompt Contracts

## MODIFIED Requirements

### Requirement: 分析师反幻觉硬规则

每个分析师提示词（fundamental、macro、technical、sentiment）MUST 包含反幻觉硬规则段，要求 LLM 仅基于输入数据推理，以数据最新日期为"现在"，不得编造数据；各分析师方法论 MUST 体现周期感知与数据时效意识。
(Previously: 仅要求反幻觉硬规则，方法论为通用静态阈值判读，未要求周期感知)

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

### Requirement: 摘要仅基于输入材料

报告摘要（report.py focus summary）与 deep_mode 对话摘要 MUST 仅基于管线上游材料/工具输出组织内容，不得引入材料外数值或知识。

#### Scenario: 摘要不得引用过期宏观数据作为最新值

- **WHEN** 管线上游宏观数据（PMI/CPI）最新日期与当前日期相差超过 3 个月
- **THEN** 摘要/分析 MUST 标注该指标数据时效滞后，不得将其表述为当前最新状态
- **AND** 相关结论 MUST 降低置信度或明示基于滞后数据

## ADDED Requirements

### Requirement: 宏观数据时效守卫

宏观数据管道 MUST 在返回数据时附带每项指标的最新数据日期与时效标记，供 LLM 判断数据是否可用于当前周期分析。

#### Scenario: 数据最新时标记为 fresh

- **WHEN** fetch_macro_indicators 返回 M2 / LPR 等最新日期距今不超过 3 个月的指标
- **THEN** 返回结构包含该指标的 as_of_date（最新数据日期）与 freshness=fresh

#### Scenario: 数据滞后时标记为 stale

- **WHEN** fetch_macro_indicators 返回 PMI / CPI 等最新日期距今超过 3 个月的指标
- **THEN** 返回结构包含该指标的 as_of_date 与 freshness=stale
- **AND** 每条记录可溯源到其自身日期（不误用相邻指标的较新日期）

#### Scenario: 字段向后兼容

- **WHEN** 既有消费方（state/fetch 下游）读取 fetch_macro_indicators 返回值
- **THEN** 新增字段不改变既有字段名与数据结构（仅追加 as_of_date / freshness 等新键），既有消费无需修改