# frontend delta: add-citation-display

## ADDED Requirements

### Requirement: 行内引用上标

报告正文中的引用标记 SHALL 渲染为行内上标编号；编号锚定后端下发的稳定 id；旧报告无引用数据时 SHALL 不渲染任何标记。

#### Scenario: 上标渲染

- **GIVEN** 报告含引用数组且正文有对应标记
- **WHEN** 渲染报告
- **THEN** 引用处 SHALL 显示上标编号，编号与后端 id 一一对应

### Requirement: 引用预览卡

hover 行内上标 SHALL 显示预览卡：claim 摘要、来源、校验状态标识（verified 绿 / failed 红 / unchecked 灰）；预览卡 SHALL 懒渲染。

#### Scenario: hover 显示状态

- **WHEN** 用户 hover 某上标
- **THEN** 预览卡 SHALL 显示该引用的 claim、来源与对应颜色的校验状态

### Requirement: 引用与校验列表

报告末尾 SHALL 提供「引用与校验」列表，按编号列出来源与校验状态；failed 项 SHALL 在视觉上可一眼区分。

#### Scenario: 列表状态可辨

- **GIVEN** 报告含 verified 与 failed 混合引用
- **WHEN** 查看列表
- **THEN** failed 项 SHALL 以红色标识，与 verified 项明显区分
