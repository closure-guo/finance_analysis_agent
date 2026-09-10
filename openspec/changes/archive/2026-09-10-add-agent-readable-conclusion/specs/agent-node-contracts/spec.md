# Delta for agent-node-contracts

## ADDED Requirements

### Requirement: 分析师报告可读结论字段

每个分析师节点输出的 `AnalystReport` 对象 SHALL 包含 `plain_conclusion` 字段：普通人可直接看懂的一句话结论+简短解释（非纯技术黑话，如「技术面偏空：MACD 死叉、反弹动能存疑，不宜右侧追入」）。该字段 SHALL 非空；LLM 输出解析失败走降级路径时 SHALL 以可读占位回填（如「技术面数据缺失，无法给出结论」），且 `parse_degraded` 照常置位。

#### Scenario: 正常输出可读结论

- **GIVEN** 分析师节点成功解析 LLM 结构化输出
- **WHEN** 产出 `AnalystReport`
- **THEN** `plain_conclusion` SHALL 为非空字符串且面向普通人可读
- **AND** `summary`（面向 RM 的精简语言）行为保持不变

#### Scenario: 解析失败降级回填

- **GIVEN** LLM 响应无法解析为合法分析师报告结构（坏 JSON 或 schema 不符）
- **WHEN** 分析师节点走降级路径产出报告
- **THEN** `plain_conclusion` SHALL 为可读占位（非空）
- **AND** `parse_degraded` SHALL 为 True，下游可识别降级来源

#### Scenario: 空值或缺失被拒绝

- **WHEN** `AnalystReport` 校验时 `plain_conclusion` 缺失或为空串
- **THEN** 校验失败（ValidationError），不得静默产出无可读结论的分析师报告