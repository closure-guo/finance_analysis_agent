# frontend delta: add-report-side-panel

## ADDED Requirements

### Requirement: 报告右侧面板

报告就绪后 SHALL 可从右侧滑出面板展示完整报告（Markdown + ECharts + 引用标记）；面板宽度 SHALL 可拖拽调节；开合状态在同一会话内 SHALL 保持。

#### Scenario: 面板打开与宽度调节

- **GIVEN** 报告已生成
- **WHEN** 用户点击「打开报告」
- **THEN** 面板 SHALL 从右侧滑出（约 300ms）
- **AND** 拖拽边缘可调节宽度

### Requirement: 消息流摘要卡片

消息流中报告 SHALL 收敛为摘要卡片：结论要点 + 「打开报告」按钮；点击 SHALL 打开右侧面板定位到完整报告。

#### Scenario: 摘要卡跳转面板

- **WHEN** 用户点击摘要卡片「打开报告」
- **THEN** 右侧面板 SHALL 打开并显示该会话完整报告

### Requirement: 面板操作栏

面板顶部 SHALL 固定操作栏：导出（docx/pptx/pdf/md）与关闭；导出行为与既有契约一致。

#### Scenario: 面板内导出

- **WHEN** 用户在面板操作栏选择导出 Word
- **THEN** 系统 SHALL 触发既有导出流程，行为与消息流内导出一致

### Requirement: 移动端回退

视口小于 768px 时 SHALL NOT 显示右侧面板，报告在消息流内全宽展示。

#### Scenario: 移动端无面板

- **GIVEN** 移动端视口
- **WHEN** 报告生成
- **THEN** 报告 SHALL 在消息流内全宽展示，不出现面板
