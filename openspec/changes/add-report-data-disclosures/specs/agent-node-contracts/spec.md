# Delta for agent-node-contracts

## ADDED Requirements

### Requirement: 报告头部行情数据截止声明

深度分析报告头部元信息 MUST 确定性渲染「行情数据截止」日期，取值 SHALL 为输入
kline 的最后一个交易日（渲染层直读 state，不经 LLM——与财务数据口径披露同一确定性
渲染纪律），使读者可从成稿直接判断行情数据新鲜度（如休市期间生成的报告应显示节前
最后交易日）。kline 缺失、为空或日期不可解析时 SHALL 省略该声明，MUST NOT 渲染
占位文案或编造日期。

#### Scenario: kline 在场时头部声明截止日期

- **GIVEN** state 含 kline 且最后一个交易日为 2026-09-30
- **WHEN** generate_report 渲染报告头部
- **THEN** 头部元信息行包含「行情数据截止: 2026-09-30」

#### Scenario: kline 缺失时省略声明

- **GIVEN** state 无 kline（或 kline 为空 DataFrame / 日期列不可解析）
- **WHEN** generate_report 渲染报告头部
- **THEN** 头部不出现「行情数据截止」字样
- **AND** 报告其余结构零变化
