# 人工验证报告: fix-dropdown-outside-close

**日期**: 2026-08-24
**验证人**: ZCode Agent（自动化浏览器验证，全程真实浏览器交互 + DOM 快照断言）
**关联 delta**: openspec/changes/fix-dropdown-outside-close/
**E2E 门禁**: 不适用（standalone `e2e/` Playwright 项目未落地，§5.6 P1–P4 未完成）；以真实浏览器人工 E2E 验证替代，证据截图落 `tests/e2e/`

## 验证环境

- 前端：`npm run dev`（Vite，http://localhost:5173），真实浏览器（ZCode In-app Browser）交互
- 覆盖组件：空状态首页（EmptyState）与会话底部输入栏（ChatInputBar）的模式/LLM 下拉框
- 新增行为：点击下拉框外部区域关闭；同一输入栏内两下拉框互斥展开；再次点击触发按钮收起
- 被测系统未 mock：页面为真实构建产物，仅通过界面操作与 localStorage（配置管理）驱动

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 空状态模式下拉框展开 → 点击外部关闭 | 是（截图 01/02） | 展开显示「快速模式/深度研究」菜单；点击标题区域外部后菜单关闭 | 点击触发按钮菜单展开；点击外部（页面标题区）菜单关闭，`快速模式` 项消失 | ✅ |
| 空状态 LLM 下拉框（无 profile）→ 打开设置 | 是 | 无 profile 时点击 LLM 切换引导打开设置面板（回归） | 点击「未配置」打开设置弹窗 | ✅ |
| 会话输入栏模式下拉框展开 | 是 | 展开显示模式菜单 | 点击「深度研究」触发按钮菜单展开（`快速模式` 可见） | ✅ |
| 会话输入栏 LLM 下拉框展开 → 点击外部关闭 | 是（DOM 断言） | 展开显示 profile 菜单；点击文本框外部关闭 | 通过设置面板另存为创建 profile「DeepSeek 办公」后，LLM 触发按钮显示 profile 名；展开后菜单项出现（同一名按钮 ×2）；点击 textarea 外部后菜单项消失（仅剩触发按钮） | ✅ |
| 同一输入栏两个下拉框互斥展开 | 是（DOM 断言） | 打开模式下拉框后再点 LLM 触发 → 模式关闭、LLM 展开；反向亦然 | 模式展开 → 点 LLM 触发 → `快速模式` 消失、LLM 菜单出现；反向验证通过 | ✅ |
| 再次点击触发按钮收起 | 是（DOM 断言） | 展开状态下再次点击同一触发按钮收起 | LLM 菜单展开后再次点击触发按钮，菜单关闭 | ✅ |
| 无 profile 点击 LLM 切换（会话视图） | 是 | 引导打开设置面板（回归） | 会话视图点击「未配置」打开设置弹窗 | ✅ |

## 异常记录

- IAB 截图接口多次超时（「previous screenshot still completing」），故部分场景以 DOM 快照断言代替截图取证；已保存两张截图证据（`tests/e2e/dropdown-outside-close-01-mode-open.png`、`-02-mode-closed.png`）
- E2E 自动门禁不可用：standalone `e2e/` Playwright 项目尚未建设（§5.6 落地路线 P1–P4 未完成），本次以真实浏览器人工 E2E 验证替代；自动化 spec（tasks.md 5.1 注明）待基础设施落地后补齐

## 结论

- [x] 全部通过，可 archive（tasks.md 5.1 自动化 E2E spec 项随 §5.6 基础设施落地后补齐；本次真实浏览器验证已覆盖对应场景）
- [ ] 存在失败项，需修复后重新验证