# 人工验证报告: fix-analysis-ux-polish

**日期**: 2026-09-05
**验证人**: ZCode agent（真实 Chromium GUI 实测 + 组件/E2E 证据归集）
**关联 delta**: openspec/changes/fix-analysis-ux-polish/
**E2E 门禁**: stub 套件 `npx playwright test --grep-invert "@live"` → 20 passed / 2 skipped / 0 failed（2026-09-05，@live 按规范归 nightly 不进门禁）

## Rebase 说明

原 delta 将 4 个需求标为 MODIFIED，但其目标需求从未进入主规范库（Aug-5 时代链路断裂）。2026-09-05 rebase：

- 「管线『已用时』计时源为后端启动时间」：已被 enhance-pipeline-progress 归档进主规范「节点已用时」（同语义，见 tests/validation/2026-08-31-enhance-pipeline-progress-validation.md），本 delta 不再重复。
- 其余 3 个需求主库无对应条目，由 MODIFIED 改为 ADDED 归档。

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 管线快照携带 pipeline_start_ts | 部分（组件/集成测试） | 快照含启动时间戳，刷新重建不归零 | tests/test_pipeline_start_ts.py（后端）+ pipelineSummary.test.tsx（前端计时源）+ streamStore updatePipelineSnapshot 实现 | ✅ |
| 澄清工具执行中发送被拦截 / 追问路径拦截生效 | 否（组件测试） | 运行中不发新请求 | 组件测试 running-guard-toast.test.tsx：追问流存活期间 composer 切换为停止按钮（send-button 移除）、Enter 不发出新 /api/analyze 请求 | ✅ |
| 警告置顶显示（fixed top-16 z-[60]、3 秒消失） | 否（组件测试） | toast 浮于 header(z-50)/输入栏(z-40) 之上 | 组件测试：经可驱动的 409 路径触发同一 showWarning 容器，断言 fixed/top-16/z-[60] + 3 秒自动消失 | ✅ |
| 流式渲染保留列表换行（与落库一致） | 否（组件测试） | 多行列表不粘连、刷新重建一致 | 组件测试 multiline-list-stream.test.tsx（复现测试 + 渲染一致性断言） | ✅ |

## 验证环境与说明

- 后端 TESTING=1 + 前端 vite（GUI 实测：深度模式思考横幅与回复正文分层渲染无错位、会话视图正常）
- 注：运行中拦截主层为 assistant-ui runtime 状态判定（adopt-assistant-ui-chat 迁移），App 层 isSessionRunning 守卫为兜底；toast 经 409 路径验证（同一 showWarning 渲染容器）。

## 结论

- [x] 全部通过，可 archive
