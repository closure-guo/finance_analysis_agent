# Delta for evaluation

## MODIFIED Requirements

### Requirement: 章节覆盖评估（section_coverage）

`SECTION_SYNONYMS` 词典 SHALL 携带版本号（`SECTION_SYNONYMS_VERSION`），冻结测试 SHALL 锁定词典内容（防止无人察觉的漂移）；prompt（`src/finance_agent/prompts/*.md`）中出现的章节性词与词典的交叉一致性 SHALL 有测试覆盖——prompt 引入词典未覆盖的章节词时测试 SHALL 红（提示更新词典或冻结版本）。

#### Scenario: 词典冻结

- **WHEN** 词典内容被修改
- **THEN** 冻结测试 SHALL 红（提示显式更新版本与冻结快照）
- **AND** 版本号随内容变更递增

#### Scenario: prompt 章节词回归

- **WHEN** prompt 中出现词典未覆盖的章节性标题词（如新增「分红能力」章节）
- **THEN** 交叉一致性测试 SHALL 红
- **AND** 修复方式 SHALL 是更新词典（或将已知英文标题显式列入 allowlist），SHALL NOT 修改测试

### Requirement: 幻觉率真值来源标注

幻觉率测量的真值数据（`data_map`）SHALL 携带 `source` 字段（快照来源与时点，如 `snapshot:akshare-2026-08-25`）；缺 source 的 data_map SHALL 被拒绝测量。真值来源 SHALL 与报告生成所用数据管道解耦（独立快照），防止「报告 vs 自己抓的数据」自证。

#### Scenario: 缺 source 拒绝

- **WHEN** 传入无 `source` 字段的 data_map
- **THEN** 测量 SHALL 报错并拒绝执行
- **AND** 错误信息 SHALL 指明需提供独立快照来源

#### Scenario: 带 source 正常测量

- **WHEN** data_map 含 `source`（如 `snapshot:akshare-2026-08-25`）
- **THEN** 测量正常执行，source 随报告输出
- **AND** 报告 SHALL 展示真值快照来源（供审计追溯）