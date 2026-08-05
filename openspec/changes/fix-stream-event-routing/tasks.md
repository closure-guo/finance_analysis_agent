# Tasks: fix-stream-event-routing

## 1. 复现测试（TDD 先行）

- [x] 1.1 新增前端测试：管线消息已存在（pipelineMsgRef 非空）时，不带 node 的 thinking_token 仍写入对话流 agentTimeline（不错位到管线卡片）
- [x] 1.2 测试 thinking_replace 在 pipelineMsgRef 非空时不被丢弃（DSML 清理生效）
- [x] 1.3 report_ready / done 后 pipelineMsgRef 置 null（逻辑已实现；由全量 154 测试无回归间接覆盖，新一轮澄清按 event.node 归属路由）
- [x] 1.4 运行确认测试失败（复现路由 bug：thinking_replace 丢弃导致 DSML 原文残留）

## 2. 事件路由修复（startAnalysis）

- [x] 2.1 thinking_token 路由条件改为按 event.node 归属：带 node 进 handleSSEEvent，否则 handleChatStreamEvent
- [x] 2.2 thinking_replace / thinking_to_answer 移除 pipelineMsgRef 判断，始终路由到对话流

## 3. 事件路由修复（resumeStream 镜像）

- [x] 3.1 resumeStream 事件分发同步应用 2.1 / 2.2 的修改

## 4. pipelineMsgRef 生命周期收口

- [x] 4.1 report_ready 事件处理处将 pipelineMsgRef 置 null（保留 pipelineMsg 展示）
- [x] 4.2 done 终态处理处将 pipelineMsgRef 置 null（startAnalysis 与 resumeStream 两处）

## 5. 验证

- [x] 5.1 `cd frontend && npx vitest run` 全部通过（154 passed，含新增 stream-event-routing.test.tsx 2 个）
- [x] 5.2 `cd frontend && npx tsc --noEmit` 无类型错误
- [ ] 5.3 E2E 门禁：真实前后端，深度模式澄清阶段流式渲染思考/工具/回复不错位、格式正常（禁 mock，走 tests/e2e/）
- [ ] 5.4 人工验证：覆盖 spec 全部新增/修改 scenario，报告落 tests/validation/
