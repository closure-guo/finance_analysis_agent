## 1. 后端 LLM 客户端：开启思考模式与 reasoning_content 解析

- [x] 1.1 `LLMResponse`（`harness/llm_client.py`）新增 `reasoning_delta: str = ""` 字段
- [x] 1.2 `LiteLLMClient._build_kwargs`（`harness/litellm_client.py`）：DeepSeek 模型将 `extra_body` 从 `{"thinking": {"type": "disabled"}}` 改为 `{"thinking": {"type": "enabled"}}`，移除 `temperature` 参数（思考模式不支持）
- [x] 1.3 `LiteLLMClient.chat_stream`：解析 chunk 的 `delta.reasoning_content`，作为 `LLMResponse(reasoning_delta=...)` 流式下发，与 `text_delta`（content）分离
- [x] 1.4 验证：真实 SSE 流确认先下发 reasoning_delta（thinking_token）再下发 text_delta（chat_token），见 7.4

## 2. 后端类型与上下文：Message 携带 reasoning_content

- [x] 2.1 `Message`（`harness/types.py`）新增 `reasoning_content: str | None = None` 字段
- [x] 2.2 `Message.to_api_dict()`：当 `reasoning_content` 非空且 `tool_calls` 非空时，输出 `reasoning_content` 字段（工具调用轮次回传）
- [x] 2.3 `ContextManager.append_assistant`（`harness/context.py`）新增 `reasoning_content` 参数，存储到 Message
- [x] 2.4 `ContextManager._strip_think_messages`（L2 压缩）：调整为清理非工具调用轮次的 reasoning_content（保留工具调用轮次的 reasoning_content）
- [x] 2.5 验证：to_api_dict 逻辑由代码审查确认（工具调用轮次输出，非工具调用轮次不输出）

## 3. 后端 harness loop：事件来源调整

- [x] 3.1 `harness/loop.py`：`LLMResponse.reasoning_delta` -> `StreamEvent.think`（THINK 事件来源从 text_delta 改为 reasoning_delta）
- [x] 3.2 `harness/loop.py`：`LLMResponse.text_delta` -> `StreamEvent.answer`（ANSWER 事件，直接作为回答）
- [x] 3.3 移除 `thinking_to_answer` / `THINK_TO_ANSWER` 逻辑（reasoning 与 content 天然分离，无需剥离）
- [x] 3.4 移除 `thinking_replace` / `THINK_REPLACE` 逻辑（原生 reasoning 无需 DSML 清理）
- [x] 3.5 工具调用轮次：`ContextManager.append_assistant` 传入 `reasoning_content`（从 LLMResponse.reasoning_delta 累积）
- [x] 3.6 验证：真实 SSE 流确认事件类型分布正确（thinking_token + chat_token，无 thinking_to_answer）

## 4. 后端 SSE 事件与持久化

- [x] 4.1 `agent_factory.py`：`LLMResponse.reasoning_delta` 下发为 `thinking_token` SSE 事件（复用现有事件，前端无需改消费逻辑）
- [x] 4.2 `agent_factory.py`：`LLMResponse.text_delta` 下发为 `chat_token` SSE 事件
- [x] 4.3 移除 `thinking_to_answer` / `thinking_replace` SSE 事件下发
- [x] 4.4 `ReplyCollector`（`api.py`）：从 `thinking_token` 累积 reasoning_content 到 thinking 字段（复用现有逻辑，来源已变更）
- [x] 4.5 移除 `ReplyCollector` 中 `thinking_to_answer` / `thinking_replace` 处理逻辑

## 5. 后端 StubLLMClient：模拟 reasoning_content

- [x] 5.1 `StubLLMClient`（`harness/stub_llm_client.py`）：先输出 `reasoning_delta`（模拟思考），再输出 `text_delta`（模拟回答）
- [x] 5.2 现有 streaming E2E 测试断言 StubLLMClient 仍输出回答文本（"这是"、"一段"等），断言不变

## 6. 前端：移除 thinking_to_answer 处理

- [x] 6.1 `App.tsx` `handleChatStreamEvent`：`thinking_to_answer` case 改为向后兼容忽略（reasoning 与 content 天然分离）
- [x] 6.2 `App.tsx` `handleChatStreamEvent`：`thinking_replace` case 改为向后兼容忽略
- [x] 6.3 `types.ts`：`ThinkingToAnswerEvent` / `ThinkingReplaceEvent` 保留类型定义（向后兼容）
- [x] 6.4 `chat_done` 时仍调用 `extractThinkingTitle` 解析 thinkingContent（thinking-stream-banner-display 成果保留）
- [x] 6.5 验证思考横幅消费 thinking_token（来源为 reasoning_content）正常展示（前端 21/21 测试通过）

## 7. 验证与 ADR

- [x] 7.1 后端单元测试：280 passed（35 failed 均为预先存在的 async 插件缺失，与本次改动无关）
- [x] 7.2 前端单元测试：21/21 通过（含 extractThinkingTitle 8、ThinkingBanner 5）
- [x] 7.3 TypeScript 类型检查：`npx tsc --noEmit` 通过
- [x] 7.4 E2E @live：快速模式 query 后思考横幅展示原生 reasoning_content（SSE 验证：thinking_token 15 个 + chat_token 24 个，无 thinking_to_answer）
- [ ] 7.5 E2E @live：深度模式澄清阶段工具调用轮次 reasoning_content 正确回传，无 400 错误（归入 nightly @live 长期验证）
- [ ] 7.6 手动落 ADR（人工维护，agent 不得自动新建）：记录"开启 DeepSeek 原生思考模式"决策
- [x] 7.7 `openspec validate enable-deepseek-thinking-mode` 通过
