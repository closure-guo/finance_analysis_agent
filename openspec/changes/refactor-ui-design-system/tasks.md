# Tasks: refactor-ui-design-system

## 1. 打底
- [x] 1.1 安装 Tailwind 并配置（content 扫描范围、确认 preflight 对旧样式的影响）
- [x] 1.2 重构前基线截图存档至 tests/validation/
- [x] 1.3 shadcn init + neutral 主题变量 + 全局字体/背景打底

## 2. 原语引入与替换
- [x] 2.1 引入 Button/Input/Textarea/Dialog/Sonner/Tooltip/DropdownMenu
- [x] 2.2 逐个替换手写通用控件，替换完成处删除对应旧 CSS
- [x] 2.3 硬编码色值清查（grep 十六进制色值，逐项改为主题变量）

## 3. 页面视觉重构（仅样式层）
- [x] 3.1 header 与输入区
- [x] 3.2 消息区/报告区容器样式（不动渲染与 SSE 逻辑）
- [x] 3.3 空态/加载态视觉统一

## 4. 图表主题
- [x] 4.1 ECharts option 色值改为主题变量注入

## 5. 验证
- [x] 5.1 逐页对比基线截图，人工验证报告落 tests/validation/
- [x] 5.2 前端全量测试无修改通过
<!-- 5.3 未勾选：E2E 门禁结论为「零新增」而非全绿（e2e 有 pre-existing 环境性失败，
     归因对比见 tests/validation/2026-08-29-refactor-ui-design-system-validation.md「E2E 失败归因」一节） -->
- [ ] 5.3 E2E 门禁
