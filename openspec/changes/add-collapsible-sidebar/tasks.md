# Tasks: add-collapsible-sidebar

## 1. 骨架
- [x] 1.1 引入 shadcn Sidebar 组件，布局容器接入 SidebarProvider
- [x] 1.2 迁移现有会话列表/新建/搜索/重命名/删除进 Sidebar 结构，功能语义不变

## 2. 折叠交互
- [x] 2.1 SidebarTrigger + Ctrl/Cmd+B 快捷键 + 200ms 宽度过渡
- [x] 2.2 折叠状态持久化，刷新/重开保持
- [x] 2.3 收起态图标栏：Logo 缩小、新建会话图标化、tooltip

## 3. 会话操作
- [x] 3.1 会话项 hover「···」菜单（重命名原地输入、删除二次确认）+ 组件测试

## 4. 移动端与入口
- [x] 4.1 移动端抽屉化 + 遮罩关闭 + 选中自动收起
- [x] 4.2 SidebarFooter 预留下载管理入口挂载位

## 5. 验证
- [x] 5.1 全量测试通过；人工验证（折叠/快捷键/持久化/移动端），报告落 tests/validation/
- [ ] 5.2 E2E 门禁（e2e/ 基建 P1–P4 未落地，门禁未生效；移动端抽屉待窄视口人工补验）
