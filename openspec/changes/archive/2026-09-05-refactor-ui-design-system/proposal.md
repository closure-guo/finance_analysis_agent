# Proposal: refactor-ui-design-system

## Why

前端为早期手写 UI，存在三个问题：

1. **观感粗糙**：无统一设计语言，颜色/圆角/间距散落硬编码，与 Kimi 等同类对话产品差距明显。
2. **维护成本高**：样式与逻辑混杂，改一处动全身，新页面开发无现成控件可复用。
3. **阻塞后续演进**：规划中的折叠侧边栏、assistant-ui 消息流、下载管理页（add-download-center）均以 shadcn/ui + Tailwind 为前提，需先完成设计系统打底。

## What Changes

- 引入 Tailwind CSS 与 shadcn/ui（组件源码入仓 `frontend/src/components/ui/`）。
- 建立设计令牌：CSS 变量主题（`--background/--foreground/--muted/--primary/--border/--radius` 等），全局字体与背景打底。
- 手写通用控件重构为 shadcn 原语：Button/Input/Textarea/Dialog/Toast(Sonner)/Tooltip/DropdownMenu。
- 报告区 ECharts 保留，option 配色改为从主题变量取值注入。
- 建立视觉回归基线：重构前对主要页面截图存档，重构后逐页对比。

非目标（Out of scope）：

- 不改变任何交互行为、路由结构、API 契约与 SSE 事件语义。
- 不拆分 App.tsx 的逻辑架构（仅样式层；结构性拆分为后续 change）。
- 不接入 assistant-ui、不实现折叠侧边栏与下载管理页（均为后续独立 change，依赖本 change）。
- 不提供暗色模式切换入口（仅预留 dark 变量）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 新增设计令牌与组件原语契约；现有页面视觉重构但交互行为不变；图表配色对齐主题；新增视觉回归基线要求。

## Impact

- **前端**：`frontend/` 新增 Tailwind/shadcn 配置与 `components/ui/`；现有组件样式层重写；ECharts option 注入主题色。
- **依赖**：tailwindcss、@radix-ui 系列、class-variance-authority、clsx、tailwind-merge、sonner、lucide-react。
- **测试**：现有组件/E2E 测试 SHALL 无修改通过（行为不变）；新增视觉基线截图。
- **验证**：视觉变更，人工验证报告落 `tests/validation/`；按红线需 E2E 门禁。
