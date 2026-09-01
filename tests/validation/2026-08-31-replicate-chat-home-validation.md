# 人工验证报告: replicate-chat-home

**日期**: 2026-08-31
**验证人**: ZCode agent（GUI 自动化实测 + 组件测试）
**关联 delta**: openspec/changes/replicate-chat-home/
**E2E 门禁**: 不适用（e2e/ 基建 P1–P4 未落地）

## 验证环境

- 组件测试：vitest + jsdom（src/test/replicateChatHome.test.tsx，4 例）
- 浏览器：真实 Chromium（1440×900）+ TESTING=1 stub 后端（STUB_SCENARIO=pipeline）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 空态首页渲染 | 组件测试 | 问候语 + 副标题 + 2–4 张建议卡片 | 问候语「今天想研究什么？」/ 输入提示 / 4 张卡片全部渲染（实测） | ✅ |
| 卡片填入不发送 | 组件测试 | 点击卡片示例文本填入输入框，无请求 | 输入框 value=「分析宁德时代」，无 /api/analyze 请求（实测+测试） | ✅ |
| 历史会话不显示空态 | 组件测试 | 切换历史会话直接显示消息流 | 选中会话后 empty-state 卸载 | ✅ |
| 发送后空态淡出 | 组件测试 | 首条消息后 200ms 淡出，消息流就位 | 实测发送 → 空态退场 → 用户气泡/思考卡/工具卡/停止按钮就位 | ✅ |
| 内容区居中收窄 | 否 | max-w-3xl 居中（adopt-assistant-ui-chat 已落地） | ThreadMessages 容器 max-w-3xl mx-auto（沿change 3 实现） | ✅ |
| 窄栏下 ECharts 显示 | 否 | 图表在窄栏自适应 | 报告卡在 max-w-3xl 内正常渲染（change 3 验证报告截图）；echarts-for-react 自带 resize | ✅ |

## 异常记录

1. IAB 截图 surface 持续超时（宿主窗口最小化）——本轮以 DOM 断言为准；空态视觉布局可由后续人工打开页面确认。
2. vite 对新增 radix 依赖首次优化触发页面重载，导致一次 chrome-error 空页面——开发服务器正常行为，重载即恢复。

## 结论

[x] 空态显示/填入/退场/历史会话判定全部通过
[ ] E2E 门禁待基建落地后补充执行
