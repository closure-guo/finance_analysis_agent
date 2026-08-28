# agent-node-contracts Specification

## Purpose

定义各 Agent 节点对 LLM 结构化输出的契约校验与降级行为：Fund Manager 决策枚举强校验与状态类型标注、报告决策中文标注、分析师解析失败降级可观测、prompt 枚举一致性、辩论角色与置信度约束，以及异常路径的测试覆盖要求。

## Requirements

### Requirement: Fund Manager Decision Enum Validation

Layer V Fund Manager 节点 SHALL 对 LLM 输出的 `decision` 字段做枚举强校验，合法值为 `approve`、`reject`、`return` 三者之一。校验前 SHALL 对原始值做归一化（去首尾空白 + 转小写），归一化后仍不在合法集内的 SHALL 抛出验证异常中断管线，SHALL NOT 降级为任何默认决策语义。

该行为与 Layer III Trader 的 `TradeDecision.model_validate` 保持一致——非法 LLM 输出属于契约违约，应显式失败而非静默放行。

#### Scenario: 合法决策值正常通过

- **WHEN** LLM 输出 `{"decision": "approve", "reasoning": "..."}`
- **THEN** 节点 SHALL 返回 `fund_manager_decision` 为 `"approve"`
- **AND** 管线继续执行至报告生成

#### Scenario: 大小写与首尾空白归一化

- **GIVEN** LLM 输出的决策值存在大小写或首尾空白差异
- **WHEN** 值为 `"Approve"`、`"APPROVE"`、`" approve "` 或 `"Return"`
- **THEN** 节点 SHALL 归一化为对应小写值并正常通过校验
- **AND** 写入 state 的值 SHALL 是归一化后的小写值

#### Scenario: 非法决策值中断管线

- **WHEN** LLM 输出的决策值归一化后仍不在 `approve` / `reject` / `return` 内（如 `"revise"`、`"拒绝"`、`"maybe"`）
- **THEN** 节点 SHALL 抛出验证异常
- **AND** SHALL NOT 将该非法值写入 state
- **AND** SHALL NOT 降级为 `approve` 或任何其他默认决策

#### Scenario: 缺失 decision 键中断管线

- **WHEN** LLM 输出的 JSON 中不含 `decision` 键
- **THEN** 节点 SHALL 抛出验证异常
- **AND** 异常 SHALL 携带可识别的字段缺失信息，而非裸 `KeyError`

#### Scenario: return 决策递增退回计数

- **WHEN** LLM 输出决策值为 `return`（或其归一化前的大小写变体）
- **THEN** 节点 SHALL 返回 `fund_manager_decision` 为 `"return"`
- **AND** SHALL 将 `return_count` 递增 1

### Requirement: Fund Manager Decision State Typing

`AnalysisState` 中的 `fund_manager_decision` 字段 SHALL 使用 `Literal["approve", "reject", "return"]` 类型标注，而非宽松的 `str` + 注释。该标注与同结构中 `analysis_type` 字段的既有风格保持一致，使静态类型检查能捕获非法赋值。

#### Scenario: 类型检查捕获非法字面量赋值

- **WHEN** 代码中向 `fund_manager_decision` 赋一个不在合法集内的字面量
- **THEN** `uv run mypy` SHALL 报告类型错误

### Requirement: Reject Decision Report Annotation

报告生成 SHALL 将 Fund Manager 的三种决策渲染为语义明确的中文标注，而非直接插入原始英文枚举值。`reject` 决策的报告 SHALL 包含「未通过审批」字样，与 ADR-0011 Layer V 的设计意图一致。

#### Scenario: reject 决策标注未通过审批

- **GIVEN** `fund_manager_decision` 为 `"reject"`
- **WHEN** 生成最终报告
- **THEN** 报告的基金经理决策章节 SHALL 包含「未通过审批」字样
- **AND** SHALL NOT 仅显示原始英文值 `reject`

#### Scenario: approve 决策标注审批通过

- **GIVEN** `fund_manager_decision` 为 `"approve"`
- **WHEN** 生成最终报告
- **THEN** 报告 SHALL 以明确的中文标注表示审批通过

#### Scenario: return 决策标注退回重评

- **GIVEN** `fund_manager_decision` 为 `"return"`
- **WHEN** 生成最终报告
- **THEN** 报告 SHALL 以明确的中文标注表示已退回交易员重新评估

### Requirement: Analyst Parse Degradation Observability

Layer I 分析师节点在 LLM 输出解析失败时 SHALL 记录 WARNING 级日志，并使降级产出的报告可被下游识别为「解析失败降级」而非「LLM 确实无 claims」。降级路径 SHALL NOT 静默发生。

该要求的动因：降级产出 `claims=[]` 会使引用校验的 `all_passed` 在零 claim 时返回 `True`，从而绕过 retry 分支直接生成报告——解析失败反而让校验「通过」，属隐蔽的静默失败。

#### Scenario: 解析失败记录告警日志

- **WHEN** LLM 响应无法解析为合法的分析师报告结构（坏 JSON 或 schema 不符）
- **THEN** 节点 SHALL 记录 WARNING 级日志，包含节点名与失败原因
- **AND** SHALL 返回降级报告以保证管线不中断

#### Scenario: 降级报告携带可识别标记

- **WHEN** 分析师节点走降级路径产出报告
- **THEN** 该报告 SHALL 携带可供下游区分的降级标记
- **AND** 引用校验 SHALL 能区分「降级导致的零 claim」与「LLM 正常输出的零 claim」

#### Scenario: claim 字段非法值改写记录告警

- **WHEN** LLM 输出的 claim 中 `claim_type` 或 `source_type` 不在合法集内
- **THEN** 系统 SHALL 记录 WARNING 级日志说明原值与改写后的值
- **AND** SHALL 继续执行既有的改写降级逻辑（`claim_type` 改写为 `entity`、`source_type` 改写为 `data`）

### Requirement: Prompt Enum Consistency

Prompt 模板中声明的枚举取值 SHALL 与代码中的合法值集合保持一致。任何在 prompt 中要求 LLM 输出、但不在代码合法集内的枚举值，SHALL 视为缺陷。

#### Scenario: 舆情分析师 claim_type 与代码一致

- **WHEN** 检查 `sentiment_analyst` prompt 中声明的 `claim_type` 取值
- **THEN** 所声明的每个值 SHALL 存在于分析师节点的 `claim_type` 合法集内
- **AND** SHALL NOT 出现导致输出被系统性静默改写的值

### Requirement: Debate Message Role Constraint

`DebateMessage` 模型的 `role` 字段 SHALL 使用 `Literal` 约束其合法角色取值，涵盖多空辩论与风控辩论的全部角色。LLM 输出的角色值不在合法集内时 SHALL 触发验证异常，而非静默透传。

该要求的动因：角色值错误会污染报告正文渲染与节点摘要提取（摘要依赖角色值过滤，值错误时摘要退化为兜底文案）。

#### Scenario: 合法角色值通过校验

- **WHEN** 辩论节点的 LLM 输出 `role` 为合法角色之一（多空双方、风控三辩论者、研究经理、风控裁决者）
- **THEN** 模型校验 SHALL 通过

#### Scenario: 非法角色值触发验证异常

- **WHEN** 辩论节点的 LLM 输出 `role` 为不在合法集内的值
- **THEN** 模型校验 SHALL 抛出验证异常
- **AND** SHALL NOT 将非法角色值写入辩论历史

### Requirement: Trade Decision Confidence Range

`TradeDecision` 模型的 `confidence` 字段 SHALL 约束取值范围为 0 到 1（含边界）。超出该范围的值 SHALL 触发验证异常。

该要求的动因：模型文档已声明 confidence 为 0-1 置信度，但缺少运行期约束。LLM 若按百分数返回（如 `95`），报告会渲染出「置信度 9500%」这类明显错误的展示。

#### Scenario: 合法置信度通过校验

- **WHEN** LLM 输出 `confidence` 为 0 到 1 之间的值（如 `0.75`）
- **THEN** 模型校验 SHALL 通过

#### Scenario: 越界置信度触发验证异常

- **WHEN** LLM 输出 `confidence` 为超出 0-1 范围的值（如 `95` 或 `-0.5`）
- **THEN** 模型校验 SHALL 抛出验证异常

### Requirement: LLM Output Exception Path Test Coverage

各 LLM 解析节点的枚举校验与降级逻辑 SHALL 有覆盖异常路径的单元测试，包括非法枚举值、缺失必填键、以及解析失败降级三类场景。

该要求的动因：TESTING stub 恒返回固定合法值，stub 管线测试对枚举漂移不敏感，故校验逻辑的有效性必须由直接针对节点的单元测试保证。

#### Scenario: Fund Manager 异常路径有测试覆盖

- **WHEN** 运行 Fund Manager 节点测试
- **THEN** 测试 SHALL 覆盖 `reject` 决策、非法枚举值、缺失 `decision` 键、大小写归一化四类场景
- **AND** 非法值与缺键场景 SHALL 断言抛出验证异常

#### Scenario: Analyst 降级路径有测试覆盖

- **WHEN** 运行分析师节点测试
- **THEN** 测试 SHALL 覆盖坏 JSON 触发降级、以及 `claim_type` / `source_type` 非法值改写两类场景
