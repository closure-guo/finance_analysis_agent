# Proposal: add-collapsible-sidebar

## Why

1. **现有侧边栏不可折叠**：固定宽度占据横向空间，阅读长报告/宽图表时内容区被压缩。
2. **交互形态落后**：Kimi 等同类产品均为「可收起为图标栏」的侧边栏，用户已形成固定心智。
3. **会话操作层级混乱**：重命名/删除等操作缺少统一的 hover 菜单形态。

## What Changes

- 侧边栏基于 shadcn/ui Sidebar（`collapsible="icon"`）重构：展开约 260px，收起约 52px 图标栏。
- 折叠触发：SidebarTrigger 按钮 + Ctrl/Cmd + B 快捷键；宽度变化 200ms 过渡；状态持久化（刷新/重开保持）。
- 收起态：Logo 缩小、「新建会话」仅显示图标、会话列表隐藏；所有图标 hover 显示 tooltip。
- 会话项操作统一为 hover 出现的「···」菜单：重命名（原地输入框）、删除（二次确认）。
- 移动端（<768px）变为抽屉式：滑入/遮罩关闭，选中会话后自动收起。
- 底部区域承载「下载管理」入口（add-download-center 已定义语义，本 change 提供挂载位置）。

非目标（Out of scope）：

- 不改变会话 store、会话 API 与持久化语义。
- 不做 Cmd/Ctrl+K 命令面板（polish-dark-mode-shortcuts）。
- 不做暗色模式切换入口。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 侧边栏折叠/展开交互、会话项操作形态、移动端抽屉行为；会话管理的功能语义不变。

## Impact

- **前端**：侧边栏组件整体重构为 shadcn Sidebar 原语；布局容器接入 SidebarProvider。
- **测试**：折叠状态持久化、快捷键、会话操作语义的组件测试。
- **验证**：交互变更，人工验证报告落 `tests/validation/`；按红线需 E2E 门禁。
