## Context

F2（已归档）建立了 E2E 门禁基础设施，但只有 smoke.spec。门禁对交互类变更未真正生效。F3a 补齐核心 spec + LLM stub。

**现状盘点**：
- F2 的 `_make_llm_client` 在 TESTING=1 时 `return None`（占位）
- LiteLLMClient 接口：`chat_stream(messages, tools, temperature, tool_choice) -> AsyncIterator[LLMResponse]`
- 快速模式（POST /api/chat）走 ReAct Agent，max_iterations=3，工具=[web_search]
- 前端无 data-testid（grep 确认），spec 需要稳定断言锚点

## Goals / Non-Goals

**Goals:**
1. LLM stub 实现：TESTING=1 时返回固定纯文本 delta（不触发 tool_call，1 轮完成）
2. 前端 5 个 data-testid 落地
3. streaming.spec / contract.spec / interaction.spec 三个 spec 跑绿
4. `npx playwright test` 全套（smoke + streaming + contract + interaction）绿

**Non-Goals:**
1. 不实现深度模式 stub（5 层管线各节点 stub 复杂度高，推迟 F3b @live）
2. 不实现 /api/test/seed 造数据逻辑（快速模式不需要预造数据）
3. 不迁移存量 pytest E2E（F3b）
4. 不接 CI（F4）

## Decisions

### D1: stub 只支持快速模式

**选择**：stub LLM 客户端返回纯文本 delta，不返回 tool_call。ReAct Agent 在第一轮收到纯文本（无 tool_call）后完成。
**理由**：快速模式的 SSE 流（thinking_token + chat_token + chat_done）是交互行为的核心验证点。深度模式 5 层管线 stub 需为每个节点返回不同响应，复杂度高且 @live 真 LLM 链路已覆盖。
**备选**：实现深度模式 stub--复杂度过高，推迟 F3b。

### D2: stub 实现为独立类 StubLLMClient

**选择**：新建 `src/finance_agent/harness/stub_llm_client.py`，实现 `chat_stream` 方法，按固定节奏（0.1s/chunk）吐固定文本。
**理由**：与 LiteLLMClient 接口一致，`_make_llm_client` 中 TESTING 分支 `return StubLLMClient()` 即可。独立文件便于维护。

### D3: 前端 testid 加在现有元素上，不改行为

**选择**：在 App.tsx 的消息渲染区域、状态指示器、错误提示、重试按钮、发送按钮上加 `data-testid` 属性。
**理由**：data-testid 是属性添加，不改 DOM 结构或行为。selector 用 data-testid 优先（E2E 红线）。

### D4: streaming.spec 用 route.abort() 模拟中断

**选择**：`page.route('**/api/chat', route => route.abort())` 模拟断连，断言 stream-error 可见 + 重试按钮可见。
**理由**：AGENTS.md 红线明确 route.abort() 不算 mock。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| stub 返回纯文本时 ReAct Agent 行为不确定 | 先写单元测试验证 stub LLMResponse 不含 tool_calls 时 Agent 在 1 轮完成 |
| 前端 testid 加错位置导致 spec 断言失败 | 先用 Playwright 探索真实 DOM 确认 selector，再写 spec |
| stub 与真 LLM 行为漂移 | F3b @live 套件 nightly 跑真 LLM 防 stub 漂移（AGENTS.md 红线要求） |
