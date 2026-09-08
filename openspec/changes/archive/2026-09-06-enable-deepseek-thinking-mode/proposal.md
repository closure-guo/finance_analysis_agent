## Why

当前系统显式禁用了 DeepSeek 原生思考模式（`litellm_client.py` 第 83-90 行 `extra_body={"thinking": {"type": "disabled"}}`），注释称"thinking mode 的 reasoning_content 与 tool calling 不兼容"。但 DeepSeek 官方文档（2025-12 起更新）已明确支持思考模式下的工具调用，仅在多轮工具调用时需将 `reasoning_content` 回传给 API。

禁用思考模式的后果：
- LLM 不产生独立的 `reasoning_content`（思维链），Langfuse trace 中无思考内容
- 前端"思考过程"展示的是 LLM 普通文本输出（`text_delta`）被 harness 当作思考，`thinking_to_answer` 时被剥离成空，用户看不到真正的思考
- 简单问题（如"沈阳天气怎么样"）LLM 直接返回回答，思考横幅一闪而过或不显示

开启思考模式后，LLM 会先输出 `reasoning_content`（独立思维链），再输出 `content`（最终回答），用户能看到真正的 LLM 推理过程。

## What Changes

- **开启 DeepSeek 思考模式**：移除 `litellm_client.py` 中 `extra_body={"thinking": {"type": "disabled"}}`，改为 `{"thinking": {"type": "enabled"}}`（或默认开启）
- **LLM 客户端解析 reasoning_content**：`LiteLLMClient.chat_stream` 解析 chunk 的 `reasoning_content` delta，作为 `LLMResponse.reasoning_delta` 流式下发
- **harness loop 处理 reasoning 事件**：将 `reasoning_delta` 作为独立 THINK 事件下发前端，与 `text_delta`（回答）分离，不再需要 `thinking_to_answer` 剥离逻辑
- **上下文管理器回传 reasoning_content**：工具调用轮次的 assistant 消息需携带 `reasoning_content` 字段回传 API（DeepSeek 要求），`Message` 新增 `reasoning_content` 字段，`to_api_dict()` 在工具调用轮次输出该字段
- **BREAKING**：现有 `thinking_to_answer` 机制（把回答文本当思考流式输出再剥离）被原生 reasoning 替代，需调整或移除

## Capabilities

### New Capabilities

- `llm-thinking-mode`：DeepSeek 原生思考模式的开启、reasoning_content 流式下发与上下文回传

### Modified Capabilities

- `frontend`：思考横幅改为消费原生 `reasoning_content`（独立思维链），而非 `text_delta` 当思考；`thinking_to_answer` 剥离逻辑不再适用
- `harness`（后端 ReAct loop）：THINK 事件来源从 `text_delta` 改为 `reasoning_content`；`thinking_to_answer` 逻辑调整

## Impact

- **后端 LLM 客户端**（`harness/litellm_client.py`）：开启思考模式、解析 `reasoning_content` delta、`LLMResponse` 新增 `reasoning_delta` 字段
- **后端 harness loop**（`harness/loop.py`）：THINK 事件来源改为 `reasoning_delta`；`text_delta` 直接作为 ANSWER；移除或调整 `thinking_to_answer` / `THINK_TO_ANSWER` 逻辑
- **后端类型**（`harness/types.py`）：`Message` 新增 `reasoning_content` 字段，`to_api_dict()` 在工具调用轮次输出该字段；`LLMResponse` 新增 `reasoning_delta`
- **后端上下文管理器**（`harness/context.py`）：`append_assistant` 接收并存储 `reasoning_content`；压缩策略 L2 清理需考虑 reasoning_content
- **后端 SSE 事件**（`agent_factory.py`）：新增 `reasoning_token` 事件类型下发 reasoning_content，或复用 `thinking_token`；移除 `thinking_to_answer` 下发
- **后端持久化**（`session_store.py` / `api.py`）：`ReplyCollector` 收集 reasoning_content 作为 thinking 持久化，不再从 text_delta 推断
- **前端**（`App.tsx` / `types.ts`）：思考横幅消费 `reasoning_token` 事件；移除 `thinking_to_answer` 处理逻辑（reasoning 与 answer 天然分离）
- **ADR**：需新增 ADR 记录"开启 DeepSeek 原生思考模式"的架构决策（手动维护，agent 不得自动新建）
- **测试**：StubLLMClient 需模拟 reasoning_content 输出；E2E 需验证真实 LLM 思考内容展示

## References

- DeepSeek 思考模式官方文档：https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
- DeepSeek V3.2 思考模式 + 工具调用支持：思考模式下可进行多轮思考与工具调用
- 工具调用轮次必须回传 `reasoning_content` 的要求：https://api-docs.deepseek.com/zh-cn/guides/thinking_mode#%E5%B7%A5%E5%85%B7%E8%B0%83%E7%94%A8
- 现有禁用决策（已过时）：`litellm_client.py` 第 83-90 行注释
