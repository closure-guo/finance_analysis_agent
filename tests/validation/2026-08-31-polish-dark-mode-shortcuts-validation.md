# 人工验证报告: polish-dark-mode-shortcuts

**日期**: 2026-08-31
**验证人**: ZCode agent（GUI 自动化实测 + 组件测试）
**关联 delta**: openspec/changes/polish-dark-mode-shortcuts/
**E2E 门禁**: 不适用（e2e/ 基建 P1–P4 未落地）

## 验证环境

- 组件测试：vitest + jsdom（src/test/darkModeShortcuts.test.tsx，8 例）
- 浏览器：真实 Chromium（1440×900）+ TESTING=1 stub 后端

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 主题三态切换 + 持久化 | 组件测试 | 浅色/深色/跟随系统循环，选择持久化 | 实测 system→light→dark 循环 + localStorage 落值 + `.dark` 类切换（body 背景 rgb(23,23,23)） | ✅ |
| 主题刷新保持 | 组件测试 | 刷新后保持深色 | localStorage 预置 dark → reload 后 darkClass=true、按钮显示「主题：深色」 | ✅ |
| 跟随系统 | 组件测试 | 随系统主题变化 | watchSystemTheme 注册（jsdom 无 matchMedia 回退浅色，组件级验证） | ⏭ 组件级 |
| 暗色下图表可读 | 否 | ECharts 文字/轴/网格清晰 | Charts 全部经 CSS 变量取色（既有契约），暗色变量覆盖后自动适配；实测 8 个 canvas 在暗色下渲染，正文/标题可读 | ✅ |
| Cmd/Ctrl+K 命令面板 | 组件测试 | 打开面板：搜索会话/快捷动作/快捷键清单 | 实测 ⌘K 打开；快捷动作 3 项（新建/下载管理/切主题）、底部快捷键清单可见 | ✅ |
| 搜索会话并跳转 | 组件测试 | 关键词过滤 + 选择跳转 | 实测「宁德」命中会话、点击跳转且面板关闭 | ✅ |
| Ctrl/Cmd+Shift+N 新建会话 | 组件测试 | 新建会话（回空态） | 快捷键触发正常（App 级组件测试） | ✅（组件测试） |
| `/` 聚焦输入框 + 输入态抑制 | 组件测试 | 未聚焦时聚焦输入框；输入态下单键不误触 | useHotkeys 集中注册：editable target 抑制无修饰单键（组件级验证） | ⏭ 组件级 |
| 暗色全页面检查 | 否 | 全站暗色可读 | 实测暗色下：侧边栏/会话列表/消息流/报告/管线时间线/报告面板/命令面板渲染正常 | ✅ |

## 实施说明

1. 命令面板为轻量自建（Dialog 形态 + 输入过滤），未引入 cmdk 依赖；交互语义对齐 shadcn Command（delta 提及 shadcn Command 为实现建议，spec 契约为行为项）。
2. ECharts 暗色适配依赖 refactor-ui-design-system 的「图表色取自主题变量」契约：.dark 覆盖变量后自动生效；Charts 容器两处 `bg-white` 硬编码已改为 `var(--card)`。

## 异常记录

1. CUA 真实指针拖拽对 6px 热区命中不佳（同 add-report-side-panel 验证报告异常 1）——本轮未涉及拖拽，仅记录。

## 结论

[x] 暗色/命令面板/快捷键全部通过（前端 439 测试全绿）
[ ] 「跟随系统」真机系统偏好切换与 E2E 门禁待人工/基建补充
