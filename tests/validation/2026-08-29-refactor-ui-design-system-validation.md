# refactor-ui-design-system 人工验证报告

> 状态：**待人工验证**（自动验证已完成，签字栏留空待用户确认）

## 概述

OpenSpec change `refactor-ui-design-system`：引入 shadcn 语义令牌层与组件原语，手写控件替换，ECharts 配色对齐主题。只改视觉不改行为。

**提交列表**（分支 `feat/design-system-download-center`）：

| 提交 | 内容 |
|---|---|
| f65d2dd | shadcn 语义令牌层打底（index.css + tailwind.config.js） |
| b4c9a24 | shadcn 原语入仓（button/input/textarea/dialog/tooltip/dropdown/sonner） |
| 75c9197 | 补 tailwindcss-animate 插件 |
| ba5084b | 手写控件替换为 shadcn 原语 |
| 820124d | ECharts 主题注入 CSS 变量 + 色值清查 |
| b3e1382 | 重构前视觉基线截图（ui-baseline/） |

## 自动验证结果

| 项 | 命令 | 结果 |
|---|---|---|
| 前端测试 | `cd frontend && npm test` | ✅ 39 files / 346 tests 全绿，**既有测试零修改** |
| 构建 | `cd frontend && npm run build` | ✅ tsc + vite 通过（4.26s） |
| E2E 门禁 | `cd tests/e2e/playwright && npx playwright test` | ⚠️ 17 failed / 8 passed / 1 skipped（见下方归因） |

### E2E 失败归因（重要）

在基线提交 `cc00bc0`（未含本分支任何改动）运行同一套件：**18 failed / 7 passed**，失败集合与本分支（17 failed）重叠，差异仅为启动抖动类的不同用例（基线多挂 smoke 健康检查 2 例，本分支多挂 explore reload 超时 1 例；explore.spec 单独重跑 3 passed）。失败模式均为 `waitForLoadState` 超时、后端会话列表缺会话——Windows 本机 8 并发 worker + vite polling 的环境性/既有问题，**本分支零引入**。失败清单存档：`.superpowers/sdd/`（e2e-baseline.log / e2e-full.log 对比）。

## 截图对比（基线 ui-baseline/ vs 重构后 ui-after/）

**采集方式补充**：会话页与报告渲染态截图由 `tests/e2e/playwright/tests/visual-baseline-report.spec.ts`
采集（STUB_SCENARIO=pipeline 管线环境，8002/5175；基线在 cc00bc0 前端源码下运行，重构后在 HEAD 运行）：

- **session-page.png**：会话页（对话流 + 分层管线时间轴运行中）
- **report-view.png**：报告渲染态（报告卡标题 + 财务图表 + 报告正文 markdown）

- **empty-state.png**：布局完全一致（侧栏/主区/输入卡/能力卡四宫格），无错位、遮挡、溢出。侧栏会话列表内容不同属数据差异（开发库会话变化），非视觉回归。
- **settings-modal.png**：结构一致（表单字段/顺序/文案不变）。预期风格变化：①遮罩加深（bg-black/80，shadcn Dialog 标准）；②右上角新增 X 关闭钮；③弹窗打开支持 Esc 关闭与焦点圈定（Radix Dialog 原生行为，属**新增交互能力**，非行为破坏——原实现无 Esc 关闭）；④控件圆角/边框统一为语义令牌。

## 遗留人工检查项

1. 真实浏览器体验：设置弹窗 Esc/X 关闭、Tab 焦点圈定是否符合预期。
2. 图表 legend/visualMap 文字色由 `--text-secondary`(#525252) 改为 `--muted-foreground`(#A3A3A3)——浅一档，确认可读性可接受（计划既定映射；若不可接受改读 `--secondary-foreground` 即可）。
3. heatmap warning 色 #F5A623→#F59E0B（`--status-warning-default`），确认可接受。
4. **grep 豁免点记录**：`Charts.tsx` `getChartTheme()` 回退区含 16 处十六进制字面量（CSS 变量缺失时的运行时回退，与原值逐一相等），与 spec「ECharts option 除外，从变量取值后注入」的意图一致，视为与 index.css 同级的豁免点（spec 的 grep 验收条款应据此理解）。
5. 下拉控件保留手写结构仅令牌化（`dropdownOutsideClick.test.tsx` 将菜单项钉死为 `role="button"`，Radix menuitem 必挂测试线）——行为不变优先于替换率的既定裁量。
6. 设置弹窗内三个原生 `<select>` 保留（真实浏览器键盘/移动端交互风险），仅令牌化。

## 人工验证签字

- [ ] 抽查通过，确认无布局破损、交互正常
- 签字/日期：____________
