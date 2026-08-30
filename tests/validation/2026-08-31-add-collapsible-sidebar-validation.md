# 人工验证报告: add-collapsible-sidebar

**日期**: 2026-08-31
**验证人**: ZCode agent（GUI 自动化实测 + 组件测试）
**关联 delta**: openspec/changes/add-collapsible-sidebar/
**E2E 门禁**: 不适用（e2e/ 基建 P1–P4 未落地，门禁尚未生效）

## 验证环境

- 组件测试：vitest + jsdom（src/test/sidebarCollapse.test.tsx，5 例）
- 浏览器：真实 Chromium（1440×900）+ TESTING=1 stub 后端

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 折叠按钮切换 | 否（组件测试） | 展开↔收起切换，过渡平滑 | data-state 切换，宽度 256↔52（实测） | ✅ |
| Ctrl/Cmd+B 快捷键 | 组件测试 | 快捷键切换 | 浏览器实测 Ctrl+B 切换生效 | ✅ |
| 折叠状态持久化 | 组件测试 | 刷新后保持收起态 | 收起→reload→仍为 52px 收起态（实测） | ✅ |
| 收起态图标栏 | 组件测试 | 新建/下载图标化 + 展开 + tooltip | 新建会话图标可用、下载图标在位；tooltip 组件级验证 | ✅ |
| 会话项「···」菜单 | 组件测试 | hover 出现，含重命名/删除 | 真实指针 hover 菜单可见；点击展开菜单（重命名/删除） | ✅ |
| 重命名原地输入 | 组件测试 | 原地输入确认后生效（PATCH） | 组件测试断言 PATCH body + UI 更新 | ✅（组件测试） |
| 删除二次确认 | 组件测试 | 先确认后 DELETE | 组件测试断言：确认前无 DELETE，确认后发出 | ✅（组件测试） |
| 移动端抽屉 | 否 | <768px 抽屉 + 遮罩关闭 + 选中收起 | matchMedia 逻辑组件级实现；IAB 视口下限 320px，未做真机验证 | ⏭ 待人工补验 |
| 主区宽度联动 | 否 | 折叠时主区 margin 52px 过渡 | 折叠/展开 margin 同步变化（width 实测联动） | ✅ |

## 异常记录

1. 验证期间 docker compose 后端与验证 stub 并存导致部分页面会话数据来自旧库——环境污染（同 adopt-assistant-ui-chat 验证报告异常 3），重命名链路以组件测试证据为准。
2. Windows 下 Playwright locator 点击在 IAB 对部分元素超时——验证工具兼容性问题，改用 CUA 坐标路径。

## 结论

[x] 桌面端折叠/持久化/快捷键/会话菜单全部通过
[ ] 移动端抽屉待真机/窄视口人工补验
[ ] E2E 门禁待基建落地后补充执行（Task 5.2 未勾选）
