# Delta for agent-evaluation-suite

## MODIFIED Requirements

### Requirement: 工具调用评估维度

工具选择正确性维度的合法工具集合 SHALL 从权威工具注册（`finance_agent.tool_registry.AGENT_TOOL_NAMES`）派生，评估器 SHALL NOT 各自硬编码一份允许集；`agent_factory` 注册工具名 SHALL 引用同一注册表常量。允许集 SHALL 仍可被评估调用方覆盖（如历史快照评估），但默认值 SHALL 与当前注册表一致。

(Previously: 允许集在 `evals/toolcall/measure.py` 硬编码 `DEFAULT_ALLOWED_TOOLS`，与 agent 实际工具注册可能漂移。)

#### Scenario: 默认与注册表一致

- **WHEN** 评估器使用默认允许集
- **THEN** 默认允许集 SHALL 等于 `tool_registry.AGENT_TOOL_NAMES`
- **AND** agent_factory 注册的工具名 SHALL 均 ∈ 注册表（注册表为准，防止评估漏注册）

#### Scenario: 覆盖保留

- **WHEN** 调用方显式传入 allowed 集合（历史快照/特定场景）
- **THEN** 以显式值生效，覆盖不改变注册表

#### Scenario: 合法集合断言

- **WHEN** 样本声明了合法工具集合且实际调用落在集合内
- **THEN** 工具选择维度通过，不因与 golden 序列不同而误判失败

#### Scenario: 循环调用检测

- **WHEN** 同一工具以相同参数连续调用超过配置上限
- **THEN** 调用效率维度扣分并在报告标注