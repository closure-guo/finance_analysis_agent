# Delta for report-decision-rendering

## ADDED Requirements

### Requirement: 数据新鲜度披露

报告头部 SHALL 包含行情数据截止声明行，标注 `state["kline"]` 最后交易日日期（确定性代码拼装，SHALL NOT 依赖 LLM 生成）。kline 缺失或为空时 SHALL 省略该行，SHALL NOT 伪造或回退到报告生成日期。

#### Scenario: 正常路径携带截止声明

- **GIVEN** state 含 kline，最后交易日为 2026-09-30
- **WHEN** 生成报告
- **THEN** 头部出现「行情数据截止: 2026-09-30」声明行

#### Scenario: kline 缺失时省略而非伪造

- **GIVEN** state 无 kline 或 kline 为空
- **WHEN** 生成报告
- **THEN** 头部不出现行情截止声明行（不回退为报告生成日期）
