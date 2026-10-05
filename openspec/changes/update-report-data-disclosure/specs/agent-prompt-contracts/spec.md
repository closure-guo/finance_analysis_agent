# Delta for agent-prompt-contracts

## ADDED Requirements

### Requirement: 板块级数据口径显式化

sentiment 分析师提示词 MUST 携带口径显式化纪律：引用板块级/市场级资金流向、涨跌幅、情绪指标时 SHALL 显式标注「板块口径」或「市场口径」及来源形态（如新闻源），MUST NOT 使用可被读作个股口径的表述；个股级数据引用 SHALL NOT 省略「个股」限定（当同段同时出现两类口径时）。

#### Scenario: sentiment prompt 携带口径纪律

- **WHEN** 加载 sentiment_analyst 提示词
- **THEN** 模板中包含「板块/市场级数据必须显式标注口径、不得与个股混写」的要求描述
