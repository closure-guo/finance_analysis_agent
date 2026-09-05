# Design: refactor-ui-design-system

## 决策

1. **shadcn/ui 而非 antd/MUI**：消费级对话产品审美（antd 为企业后台风格，改造成本高）；组件源码入仓可被 coding agent 直接读写；与后续 assistant-ui 接入生态闭环。
2. **渐进共存而非推倒**：Tailwind 与旧样式共存，按「通用控件 → 页面区域」顺序替换，替换完成的区域删除对应旧 CSS；共存期样式冲突通过 Tailwind preflight 确认与局部作用域隔离解决。
3. **ECharts 不迁移**：图表能力与交互成熟，不迁 recharts；仅将 option 中的色值改为从 CSS 变量读取注入。
4. **主题以 neutral 起步**：先用 shadcn 默认 neutral 主题上线，后续可用 tweakcn 等工具可视化调色，只改 CSS 变量不动组件。

## 风险

- **共存期样式污染**：Tailwind preflight 会重置部分旧样式 → 打底阶段先全局截图存档，逐页核对。
- **视觉回归无基线**：重构前截图存档至 `tests/validation/` 作为对比基准，否则「无布局破损」无法验收。
- **agent 顺手改行为**：以「现有测试无修改通过」作为硬约束写进 spec，锁住行为语义。
