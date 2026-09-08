# citation-verification delta: add-citation-display

## ADDED Requirements

### Requirement: 校验结果结构化下发

系统 SHALL 在报告就绪时随事件/会话数据下发结构化引用数组；每项 SHALL 包含稳定 `id`、`claim`、`source`、`verdict`（verified/failed/unchecked）与 `detail`；无引用或旧数据缺省该字段时 SHALL 正常返回，不报错。

#### Scenario: 报告携带引用数组

- **GIVEN** 一次深度分析完成且经过引用校验
- **WHEN** 报告就绪事件发出
- **THEN** 负载中 SHALL 含引用数组，每项含上述五字段

#### Scenario: 旧数据兼容

- **GIVEN** 无引用字段的历史会话
- **WHEN** 前端读取该会话
- **THEN** 系统 SHALL 正常返回，引用字段缺省
