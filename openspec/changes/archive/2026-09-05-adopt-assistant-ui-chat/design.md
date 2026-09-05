# Design: adopt-assistant-ui-chat

## 决策

1. **以官方模板为基座搬运，而非照文档从零搭**：`npx assistant-ui@latest create -t langgraph` 产出完整可运行参考实现，组件配置、流式接线、样式均已调通；本项目从中搬运组件与配置，只重写 adapter，把 bug 风险集中在最窄的接口面。
2. **adapter 为唯一手写层，且设计为纯函数**：`translate(event) → message parts`，输入后端 SSE 事件、输出 UI 状态，不含副作用；逐事件类型单测覆盖，未知事件安全忽略（forward-compatible）。
3. **后端协议不动**：所有适配在前端完成，后端 SSE 事件流保持现状，避免触碰已稳定的管线/辩论/citation 事件。
4. **独有功能走自定义部件**：管线时间线、ECharts、导出按钮以 assistant-ui 自定义消息部件挂载，不复用其内置形态。

## 风险

- **事件遗漏**：adapter 漏映射某类事件导致 UI 静默丢内容 → 事件类型枚举 + 逐类型单测 + 未知事件 debug 日志。
- **中断/重连续传**：现有停止生成与刷新重建语义必须在 assistant-ui runtime 下复刻 → 以 fix-analysis-ux-polish 的行为契约为验收基准。
- **既有测试失效**：消息区 DOM 结构变化可能使部分选择器类测试失败 → 允许更新选择器，但 SHALL NOT 修改断言语义。
