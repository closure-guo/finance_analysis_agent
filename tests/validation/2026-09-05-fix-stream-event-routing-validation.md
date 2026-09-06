# 人工验证报告: fix-stream-event-routing

**日期**: 2026-09-05
**验证人**: ZCode agent（真实 Chromium GUI 实测 + 组件/E2E 证据归集）
**关联 delta**: openspec/changes/fix-stream-event-routing/
**E2E 门禁**: stub 套件 `npx playwright test --grep-invert "@live"` → 20 passed / 2 skipped / 0 failed（2026-09-05，@live 按规范归 nightly 不进门禁）

## 验证环境

- 后端 TESTING=1（独立测试库 data/gui-test-sessions.db，LLM stub）
- 前端 vite dev server，Chromium 1280×800

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 澄清阶段走对话流 | 是（thinking-timeline-deep / streaming spec 家族） | 澄清阶段思考/回复走对话消息流 | GUI 实测：深度模式发送「帮我分析一下」，回复即时入列（会话创建 + 消息渲染） | ✅ |
| 思考过程在澄清阶段走对话流 | 部分（thinking-banner.spec @live 除外，thinking-timeline 组件/E2E 覆盖） | 思考内容以 ThinkingBanner 呈现于对话流，不误挂管线 | GUI 实测：「分析思路」折叠卡渲染思考内容（「用户询问了一个测试问题…」），后接回复正文，二者分层无错位 | ✅ |
| 管线节点思考按 node 归属进管线 UI | 是（thinking-timeline-pipeline.spec.ts，门禁绿） | 有 node 的 thinking 归管线时间轴 | E2E + 组件测试（pipelineThinking.test.ts）覆盖 | ✅ |
| thinking_replace / thinking_to_answer 不被管线状态丢弃 | 是（agentTimeline / deserializeTimeline 组件测试） | 替换/转正事件不丢失 | 组件测试全绿（2026-09-05 前端全量 487/487） | ✅ |
| run_deep_analysis 触发管线 UI / awaiting_input 澄清等待 / pipelineMsgRef 收口 | 是（streaming.spec + session-switch-resumption + refresh-concurrent-misalignment 均门禁绿） | 管线生命周期正确 | stub 门禁全绿覆盖 | ✅ |

## 异常记录

无失败项。注：thinking-banner.spec 的 3 个 @live 用例（真 LLM）在 stub 门禁中排除，按规范归 nightly 长期验证，不影响本门禁结论。

## 结论

- [x] 全部通过，可 archive
