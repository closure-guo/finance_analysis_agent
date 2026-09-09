# Delta for frontend

## ADDED Requirements

### Requirement: 明日方舟 UI 主题配色

系统 SHALL 以明日方舟 UI 色卡（#2F3132 深灰面板、#FCFBFB 纯白、#228EBF 强调蓝、#CBB54C 点缀金）作为全部主题设计令牌的主取值来源；罗德岛阵营色卡（#0A0B0D 罗德岛黑、#2A5BA8 罗德岛蓝、#3FC6E0 亮青蓝、#888A8C 工业灰、#F5F5F5 医疗白）SHALL 仅作点缀取值。取值 SHALL 集中于 `frontend/src/index.css` 的明暗两套 CSS 变量；对比度不足处 SHALL 使用同色相衍生色阶（如深色链接提亮、浅色链接加深），衍生规则 SHALL 在令牌注释中说明。历史 TRAE 品牌紫（#4B3FE3/#6C5FF0/#8F84F5）SHALL NOT 出现于任何前端源文件。

#### Scenario: 浅色主题映射

- **GIVEN** 浅色主题生效
- **WHEN** 渲染任意页面
- **THEN** 页面画布 SHALL 为 #FCFBFB 系纯白、正文 SHALL 为罗德岛黑 #0A0B0D
- **AND** 按钮/链接/焦点环 SHALL 为强调蓝 #228EBF，警告与中性标签 SHALL 为点缀金 #CBB54C

#### Scenario: 深色主题映射

- **GIVEN** 深色主题生效
- **WHEN** 渲染任意页面
- **THEN** 页面底色 SHALL 为深灰面板 #2F3132（卡片/浮层为其亮阶衍生），文字 SHALL 为纯白 #FCFBFB
- **AND** 按钮/气泡/标签主色 SHALL 为强调蓝 #228EBF，分析节点运行态 SHALL 以亮青蓝 #3FC6E0 点缀（边框 + 辉光）

#### Scenario: 调色板契约被测试冻结

- **GIVEN** themePalette 冻结测试（frontend/src/test/themePalette.test.ts）
- **WHEN** 任何人对 index.css 引入历史品牌紫或偏离色卡的主令牌值
- **THEN** 前端测试 SHALL 变红阻止合入

#### Scenario: 图表配色对齐色卡

- **GIVEN** 图表 option 从主题 CSS 变量取色（既有「图表配色对齐主题」机制）
- **WHEN** 渲染报告图表
- **THEN** 冷色系列 SHALL 取强调蓝（--chart-sky）、罗德岛蓝（--chart-violet）、亮青蓝（--chart-teal），琥珀系列 SHALL 取点缀金（--chart-amber）
- **AND** 涨跌语义暖色（coral/mint/rose）SHALL 保持原值不变
- **AND** 深色主题下冷色系 SHALL 使用提亮衍生值保证曲线可读

#### Scenario: 组件无散落硬编码色

- **GIVEN** 任意前端组件
- **WHEN** 检查其样式来源
- **THEN** 语义状态色 SHALL 来自 CSS 变量或语义令牌类（如 text-[color:var(--status-error-default)]），SHALL NOT 使用 Tailwind 调色板类（text-red-500 等）或 ECharts 外的十六进制字面量
