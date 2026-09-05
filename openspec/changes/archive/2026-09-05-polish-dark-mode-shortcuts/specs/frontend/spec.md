# frontend delta: polish-dark-mode-shortcuts

## ADDED Requirements

### Requirement: 暗色模式

系统 SHALL 提供浅色/深色/跟随系统三种主题选择，入口位于侧边栏底部；选择 SHALL 持久化；暗色下所有页面（含 ECharts 图表与报告）SHALL 保持可读。

#### Scenario: 主题持久化与跟随系统

- **GIVEN** 用户选择深色
- **WHEN** 刷新页面
- **THEN** 深色主题 SHALL 保持；选择「跟随系统」时 SHALL 随系统主题变化

#### Scenario: 暗色下图表可读

- **WHEN** 暗色模式下查看含 ECharts 的报告
- **THEN** 图表文字、坐标轴、网格线 SHALL 清晰可辨

### Requirement: 命令面板

Cmd/Ctrl+K SHALL 打开命令面板：可按标题搜索会话并跳转；SHALL 提供快捷动作（新建会话、打开下载管理、切换主题）；面板底部 SHALL 列出可用快捷键。

#### Scenario: 搜索并跳转会话

- **GIVEN** 存在多个历史会话
- **WHEN** 用户在命令面板输入关键词并选择结果
- **THEN** 应用 SHALL 切换到对应会话

### Requirement: 快捷键与输入态抑制

Ctrl/Cmd+Shift+N SHALL 新建会话；`/` 在输入框未聚焦时 SHALL 聚焦输入框；输入框聚焦时单键快捷键 SHALL NOT 触发。

#### Scenario: 输入中不误触

- **GIVEN** 输入框处于聚焦状态
- **WHEN** 用户输入 `/`
- **THEN** 字符 SHALL 正常输入，不触发快捷键
