# Delta for agent-evaluation-suite

## ADDED Requirements

### Requirement: 评估材料优先展示分析师可读结论

评估材料（judge 输入变量 `analyst_reports` 的拼装、人工标注导出表的 agent 摘要）SHALL 优先使用分析师报告的 `plain_conclusion`（普通人可读的结论+解释）；旧 trace 报告对象无该字段时 SHALL 回退现状（`summary` 拼贴），不得报错或中断评估。评估材料 SHALL NOT 以「正文前 N 字符」截取的方式充当该层摘要（与原文重复、无信息量）。

#### Scenario: 新报告展示可读结论

- **GIVEN** 分析师报告对象含非空 `plain_conclusion`
- **WHEN** 拼装 analyst_reports judge 变量或生成标注材料 agent 摘要
- **THEN** 该 agent 的展示文本 SHALL 取自 `plain_conclusion`
- **AND** `summary` 不再作为该 agent 的默认展示文本

#### Scenario: 旧 trace 回退

- **GIVEN** 分析师报告对象缺 `plain_conclusion`（旧版本产出）
- **WHEN** 拼装评估材料
- **THEN** SHALL 回退使用 `summary`（或 `conclusion`），不报错、不中断评估

#### Scenario: 禁止截取式摘要

- **WHEN** 生成人工标注材料
- **THEN** 评估材料 SHALL NOT 用「正文前 N 字符」充当该层摘要
- **AND** 分析师节以「各 agent 的 plain_conclusion（或回退 summary）」分行展示