# Proposal: polish-dark-mode-shortcuts

## Why

1. **暗色变量已预留但未启用**：refactor-ui-design-system 建立了 dark 变量，缺少切换入口与图表适配，长时阅读（尤其晚间）体验缺失。
2. **会话多了找不动**：历史会话检索只有侧边栏搜索框，缺 Kimi/主流产品标配的 Cmd/Ctrl+K 命令面板。
3. **键盘动线不完整**：已有 Ctrl/Cmd+B（折叠侧边栏），缺新会话、聚焦输入框等高频快捷键。

## What Changes

- 暗色模式：侧边栏底部加主题切换（浅色/深色/跟随系统），选择持久化；全站含 ECharts 图表在暗色下可读（图表色取自主题变量的既有契约生效）。
- Cmd/Ctrl+K 命令面板（shadcn Command）：搜索会话标题并跳转、快捷动作（新建会话、打开下载管理、切换主题）。
- 快捷键补齐：Cmd/Ctrl+K 命令面板、Ctrl/Cmd+Shift+N 新建会话、`/` 聚焦输入框（输入框聚焦时不触发）；界面内提供快捷键提示（命令面板底部列出）。

非目标（Out of scope）：

- 不做自定义主题色编辑器。
- 不做快捷键自定义映射。
- 不改变任何后端契约。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 新增暗色模式切换与命令面板/快捷键契约；既有交互语义不变。

## Impact

- **前端**：主题切换组件、命令面板、快捷键注册表。
- **测试**：主题持久化、图表暗色可读、快捷键触发的组件测试。
- **验证**：人工验证报告落 `tests/validation/`。
