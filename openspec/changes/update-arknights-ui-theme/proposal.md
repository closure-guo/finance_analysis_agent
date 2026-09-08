# Proposal: update-arknights-ui-theme

## Why
用户要求前端 UI 整体换装：以明日方舟游戏 UI 色卡为主色调（深灰面板 #2F3132、纯白 #FCFBFB、强调蓝 #228EBF、点缀金 #CBB54C），罗德岛阵营色卡（#0A0B0D/#2A5BA8/#3FC6E0/#888A8C/#F5F5F5）退为少量点缀，替换现 TRAE Work 品牌紫视觉。用户已通过浏览器预览明暗双主题并确认定稿（2026-09-08 会话）。

## What Changes
- `frontend/src/index.css` 明暗两套设计令牌全部重映射为明日方舟 UI 色卡（浅色：纯白画布 + 强调蓝主色 + 罗德岛黑正文；深色：深灰面板底 + 纯白文字 + 强调蓝主色 + 点缀金标签）
- 罗德岛阵营色点缀位：亮青蓝 `#3FC6E0` = 分析节点运行态辉光、罗德岛蓝 `#2A5BA8` = 图表系列色、工业灰 `#888A8C` = 三级文字、罗德岛黑 `#0A0B0D` = 浅色正文与反色块
- 图表系列色对齐色卡（sky=强调蓝、amber=点缀金、violet=罗德岛蓝、teal=亮青蓝），涨跌语义暖色（coral/mint/rose）保持不变；深色下冷色系提亮衍生保证曲线可读
- **BREAKING（视觉层）**: 旧 TRAE 品牌紫（#4B3FE3/#6C5FF0/#8F84F5）全量清除，由 themePalette 冻结测试守门
- 硬编码色收敛（非行为变更）：tailwind.config 品牌色改引 CSS 变量；Charts.tsx 回退值同步色卡并导出 `cssVar`；trackRecord 三页 ECharts antd 色改从变量取值；DecisionCenter/App/trackRecord 散落 Tailwind 调色板类改语义令牌类
- 附带修复一处既有缺陷：`TrackRecordPage` 高回撤警示 style 中误用 Tailwind 类名字符串作为 CSS 颜色值（无效值被浏览器忽略，警示色从未生效），改为 `var(--status-error-default)`
- 附带修复一处既有构建损坏（#115 合并引入，HEAD 上即红）：`PredictionRecord` 类型补缺失的 `rationale_snapshot?: unknown` 字段

## Capabilities
- **New Capabilities**: 无
- **Modified Capabilities**: frontend（新增「明日方舟 UI 主题配色」requirement；既有「设计令牌为样式唯一来源」「图表配色对齐主题」「主题三态选择」requirement 语义不变，仍完全适用）

## Impact
仅前端视觉层：`frontend/src/index.css`、`tailwind.config.js`、`Charts.tsx`、`types.ts`（一行类型补全）、trackRecord 三页、`DecisionCenter.tsx`、`App.tsx` 局部类名、新增 `themePalette.test.ts` 与 `vite-env.d.ts`。无后端/API/SSE/状态流转变更；三态主题切换机制（localStorage `fa_theme` + `.dark` 类）不变。
