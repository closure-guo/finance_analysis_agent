# Design: add-collapsible-sidebar

## 决策

1. **shadcn/ui Sidebar 原语**：内置 icon 折叠、快捷键、状态 cookie 持久化、移动端抽屉，避免手写布局状态机；与 refactor-ui-design-system 的设计令牌同源。
2. **状态持久化用 cookie/localStorage**：折叠状态属纯 UI 偏好，不入后端会话数据。
3. **会话操作收进 hover 菜单**：重命名/删除从常驻按钮改为「···」菜单，与 Kimi 形态对齐，降低列表视觉噪音。

## 风险

- **与 add-download-center 的入口位置耦合**：下载管理入口应挂进 SidebarFooter，两个 change 实施顺序错位时入口暂挂原位置，语义不变。
- **布局抖动**：宽度过渡期间内容区重排 → 过渡仅作用于侧边栏宽度，内容区用 flex 自适应，验收含"无闪烁抖动"。
