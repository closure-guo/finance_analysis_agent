# frontend delta: refactor-ui-design-system

## ADDED Requirements

### Requirement: 设计令牌为样式唯一来源

所有颜色、圆角、阴影 SHALL 引用 shadcn 主题 CSS 变量（`--background/--foreground/--muted/--primary/--border/--radius` 等）；组件内 SHALL NOT 出现硬编码色值（ECharts option 除外，其 SHALL 从变量取值后注入）。

#### Scenario: 重构后组件无硬编码色值

- **GIVEN** 任意完成重构的组件
- **WHEN** 检查其样式定义
- **THEN** 颜色与圆角 SHALL 来自主题变量或 Tailwind 语义类（bg-background、text-muted-foreground 等）
- **AND** 不存在十六进制色值硬编码

### Requirement: 通用控件统一为 shadcn 原语

按钮、输入框、多行输入、对话框、toast、tooltip、下拉菜单 SHALL 使用 `components/ui/` 下的 shadcn 原语；替换 SHALL 保持既有交互行为（提交、校验、快捷键、禁用态、加载态）不变。

#### Scenario: 控件替换后行为一致

- **GIVEN** 某手写控件已替换为 shadcn 原语
- **WHEN** 用户执行点击/输入/禁用/hover 交互
- **THEN** 行为与原实现一致，包括加载态与禁用态表现

#### Scenario: 现有测试无修改通过

- **GIVEN** 重构完成
- **WHEN** 运行前端全量测试
- **THEN** 所有既有测试 SHALL 在不修改断言语义的前提下通过

### Requirement: 全局视觉打底

全局 SHALL 应用主题变量定义的背景色、前景色与统一字体栈；header、输入区、内容区底色 SHALL 取自 `--background/--muted` 语义层级。

#### Scenario: 全局底色与字体生效

- **WHEN** 打开任意页面
- **THEN** 背景与文字颜色来自主题变量
- **AND** 字体栈全局统一，无页面级字体覆盖

### Requirement: 图表配色对齐主题

报告区 ECharts SHALL 保留且交互不变；其 option 中的主色、坐标轴色、网格线色 SHALL 从主题 CSS 变量取值注入，与页面视觉一致。

#### Scenario: 图表色随主题变量变化

- **GIVEN** 主题变量被调整（如切换配色方案）
- **WHEN** 渲染报告图表
- **THEN** 图表主色与新主题一致，无需修改图表代码

### Requirement: 视觉回归基线

重构前 SHALL 对主要页面（会话页、报告渲染态、空态）截图存档至 `tests/validation/`；重构后 SHALL 逐页对比，确认无布局破损。

#### Scenario: 重构后无布局破损

- **GIVEN** 重构完成且基线截图已存档
- **WHEN** 逐页对比基线与新截图
- **THEN** 仅视觉风格变化，无元素错位、遮挡或溢出

## MODIFIED Requirements

（无——本 change 只改视觉呈现，不修改既有行为契约的语义）
