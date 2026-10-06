# Delta for agent-prompt-contracts

## ADDED Requirements

### Requirement: 舆情分析师外部口径显式化

sentiment_analyst 提示词 MUST 携带外部口径显式化约束：新闻源引用的资金流、成交额、
涨跌幅等市场数据常为板块/行业/全市场口径而非个股口径，出现在个股报告语境时提示词
MUST 要求表述显式标注口径主体与来源属性（如「科创板板块整体主力资金净流入 10.31
亿元（新闻源口径）」），MUST NOT 使读者误读为该个股自身的资金流；口径主体无法从
新闻确认时 SHALL 标注「口径主体未明」并降权使用该数据。

#### Scenario: sentiment prompt 携带口径显式化约束

- **WHEN** 加载 sentiment_analyst 提示词
- **THEN** 模板中包含「板块/行业/全市场口径的市场数据须显式标注口径主体与来源属性」的要求描述
- **AND** 模板包含个股报告语境下的反误读示例（口径主体 + 新闻源口径标注）
- **AND** 模板包含「口径主体未明」时的降权处理要求
