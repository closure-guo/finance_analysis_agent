# 人工验证报告: fix-sidebar-content-overflow

**日期**: 2026-10-01
**验证人**: ZCode（自动执行 + E2E 真实浏览器）
**关联类型**: 修 bug · 意图不变（A 类，systematic-debugging；不触碰 openspec）
**E2E 门禁**: tests/e2e/playwright（sidebar-content-overflow.spec.ts 绿，默认 config 8000）

## 用户报告

侧边栏展开态下，「新建分析」按钮与「搜索股票」输入框宽度超过侧边栏 256px，右缘被 aside 的 overflow-hidden 裁掉（长会话名场景）。

## 根因

会话行 display_name 为 truncate（white-space: nowrap），长会话名的 min-content ≈ 全文宽度；展开态 rail 根（`flex flex-col h-full`）是行向 flex 容器（sidebar.tsx 显隐包裹层 display:flex）的 flex item，`min-width:auto` 使其拒绝收缩到内容 min-content（~403px）以下，整个 rail 被撑宽溢出，rail 内所有 w-full 子元素（按钮/输入框）跟随拉伸后被裁剪。

## 变更清单

| 文件 | 变更 |
|---|---|
| `frontend/src/App.tsx` | 展开态 rail 根加 `min-w-0`（附注释锚点），恢复 flex item 收缩能力 |
| `tests/e2e/playwright/tests/sidebar-content-overflow.spec.ts` | 新增复现 spec（红→绿）+ 幂等预清理加固（见异常记录） |

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 长会话名不撑破侧栏 | 是（sidebar-content-overflow.spec.ts：/api/test/seed 写真实长名会话） | 新建按钮/搜索框 ≤233px、会话名 ≤217px、名 div 唯一 | 干净测试库上通过（8.2s / 9.3s 两轮） | ✅ |
| 常规会话名不回归 | 是（同 spec 断言口径对任意内容成立；vitest 既有侧栏用例） | 布局不变 | 通过 | ✅ |
| 前端单测 / 类型 | 否 | vitest 全绿、tsc -b 无错 | 75 文件 622 用例全过；tsc 通过（2026-10-01 新鲜运行） | ✅ |
| 既有面板/缩放 E2E 不回归 | 部分（report-panel-overlay.spec.ts + pipeline-graph-zoom.spec.ts 同批复跑） | 全绿 | 2 passed（1.7m，timeline 套件 8002/5175） | ✅ |

## 异常记录

- **遗留种子会话污染**：首两轮运行 `toHaveCount(1)` 收到 2——持久化测试库（`data/test-e2e-sessions.db`）存有上次会话中断运行遗留的同名种子会话（finally 清理未执行/失手）。按根因加固 spec：运行前按 display_name 幂等预清理遗留种子 + finally 删除改 best-effort（`catch(() => {})`，删除失手不掩盖原断言失败，遗留由下次运行自愈）。**未放宽任何断言**（宽度口径 233/217 与 count=1 原样保留），加固后干净库两轮全绿。

## 结论

[x] 全部通过，可提交
