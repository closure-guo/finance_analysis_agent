# Tasks: add-e2e-core-specs

## 1. 后端 LLM stub 实现

- [ ] 1.1 新建 `src/finance_agent/harness/stub_llm_client.py`：`StubLLMClient` 类，实现 `chat_stream` 方法，按 0.1s/chunk 节奏吐固定文本 delta（不返回 tool_call，1 轮完成）
- [ ] 1.2 修改 `src/finance_agent/agent_factory.py:_make_llm_client`：TESTING 分支替换 `return None` 为 `return StubLLMClient()`
- [ ] 1.3 单元测试：验证 StubLLMClient.chat_stream 返回固定文本 + is_finished=True + 无 tool_calls

## 2. 前端 data-testid 落地

- [ ] 2.1 在 `frontend/src/App.tsx` 添加 data-testid：stream-output（消息渲染区域）、stream-status（流式指示器）、stream-error（错误提示）、retry-button（重试按钮）、send-button（发送按钮）
- [ ] 2.2 验证前端无行为变化（vitest 全绿）

## 3. streaming.spec（3 场景）

- [ ] 3.1 创建 `tests/e2e/playwright/tests/streaming.spec.ts`：快速模式流式增量渲染 + 指示器生命周期
- [ ] 3.2 创建中断恢复场景：route.abort() 拦截 + stream-error + retry-button 可见
- [ ] 3.3 跑 `npx playwright test streaming` 全绿

## 4. contract.spec（1 场景）

- [ ] 4.1 创建 `tests/e2e/playwright/tests/contract.spec.ts`：验证 POST /api/chat 请求体 + SSE 响应头
- [ ] 4.2 跑 `npx playwright test contract` 全绿

## 5. interaction.spec（1 场景）

- [ ] 5.1 创建 `tests/e2e/playwright/tests/interaction.spec.ts`：发送中按钮禁用 + opacity 0.5
- [ ] 5.2 跑 `npx playwright test interaction` 全绿

## 6. 全套验证 + 文档同步

- [ ] 6.1 跑 `npx playwright test` 全套（smoke + streaming + contract + interaction）全绿
- [ ] 6.2 跑 `uv run pytest` 单元测试全绿（含新 stub 测试）
- [ ] 6.3 人工验证报告落 `tests/validation/2026-07-26-add-e2e-core-specs-validation.md`
