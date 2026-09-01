# frontend delta: add-collapsible-sidebar

## ADDED Requirements

### Requirement: 侧边栏可折叠

侧边栏 SHALL 支持展开态（约 260px）与收起态（约 52px 图标栏）切换；触发方式 SHALL 包括折叠按钮与 Ctrl/Cmd + B 快捷键；宽度变化 SHALL 带约 200ms 过渡；折叠状态 SHALL 持久化，刷新与重开后保持。

#### Scenario: 按钮与快捷键均可切换

- **WHEN** 用户点击折叠按钮或按下 Ctrl/Cmd + B
- **THEN** 侧边栏 SHALL 在展开/收起间切换，过渡平滑无抖动

#### Scenario: 折叠状态持久化

- **GIVEN** 用户已收起侧边栏
- **WHEN** 刷新页面
- **THEN** 侧边栏 SHALL 保持收起态

### Requirement: 收起态图标栏

收起态下 SHALL 仅保留图标：Logo 缩小、「新建会话」显示为图标按钮；所有图标 hover SHALL 显示 tooltip 文字；新建会话功能在收起态 SHALL 可用。

#### Scenario: 收起态新建会话可用

- **GIVEN** 侧边栏处于收起态
- **WHEN** 用户点击新建会话图标
- **THEN** 系统 SHALL 创建新会话，行为与展开态一致

### Requirement: 会话项操作形态

会话项 hover 时 SHALL 在右侧出现「···」菜单，含重命名与删除；重命名 SHALL 为原地输入框；删除 SHALL 二次确认；操作的后端语义与现状一致。

#### Scenario: hover 菜单操作

- **GIVEN** 会话列表存在会话
- **WHEN** 用户 hover 某会话并打开「···」菜单选择重命名
- **THEN** 标题 SHALL 变为原地输入框，确认后生效
- **AND** 选择删除时 SHALL 先弹确认，确认后从列表移除

### Requirement: 移动端抽屉

视口宽度小于 768px 时侧边栏 SHALL 变为抽屉：默认隐藏，从左侧滑入；点击遮罩或选中会话后 SHALL 自动关闭。

#### Scenario: 移动端选中后收起

- **GIVEN** 移动端视口且抽屉已打开
- **WHEN** 用户点击某会话
- **THEN** 抽屉 SHALL 自动关闭并切换到该会话
