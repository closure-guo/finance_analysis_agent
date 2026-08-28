# llm-thinking-mode Specification

## Purpose

定义 DeepSeek 原生思考模式集成：LLM 输出独立的 `reasoning_content`（思维链）与 `content`（最终回答），经 `thinking_token` / `chat_token` 事件分离流式下发，前端展示真实 LLM 推理过程而非将回答文本当作思考，不再使用 `thinking_to_answer` 剥离机制。

## Requirements

### Requirement: DeepSeek Thinking Mode Integration

系统 SHALL 开启 DeepSeek 原生思考模式，LLM 输出独立的 `reasoning_content`（思维链）与 `content`（最终回答）分离，前端展示真正的 LLM 推理过程而非将回答文本当作思考。

#### Scenario: 开启思考模式并流式下发 reasoning_content

- **GIVEN** LLM 客户端为 DeepSeek 且思考模式已开启
- **WHEN** LLM 流式响应包含 `reasoning_content` delta
- **THEN** LLM 客户端 SHALL 将 `reasoning_content` delta 作为 `reasoning_delta` 流式下发
- **AND** harness loop SHALL 将 `reasoning_delta` 转为 THINK 事件下发前端
- **AND** `reasoning_content` 与 `content`（text_delta）分离，不再用 `thinking_to_answer` 剥离

#### Scenario: 工具调用轮次回传 reasoning_content

- **GIVEN** LLM 在思考模式下进行工具调用，assistant 消息包含 `reasoning_content` 与 `tool_calls`
- **WHEN** 后续请求构建 API 消息列表
- **THEN** 带 `tool_calls` 的 assistant 消息 SHALL 输出 `reasoning_content` 字段回传 API
- **AND** 非 tool_calls 的 assistant 消息 SHALL NOT 输出 `reasoning_content`（API 忽略，节省 token）
- **AND** 避免触发 DeepSeek API 的 400 "Missing reasoning_content" 错误

#### Scenario: 思考内容持久化来源变更

- **GIVEN** LLM 思考模式下产生 `reasoning_content`
- **WHEN** 会话结束时持久化 assistant 回复到 chat_history
- **THEN** thinking 字段 SHALL 存储从 `reasoning_content` 收集的思考内容
- **AND** 不再从 `text_delta`（content）推断思考内容
- **AND** 历史会话恢复时思考横幅展示原生 reasoning 内容

#### Scenario: 非工具调用轮次无需 thinking_to_answer

- **GIVEN** LLM 思考模式下输出 reasoning_content 后直接输出 content（无工具调用）
- **WHEN** reasoning_content 与 content 流式下发完成
- **THEN** 前端思考横幅直接消费 reasoning_content（thinking_token 事件）
- **AND** 前端回答区直接消费 content（chat_token 事件）
- **AND** SHALL NOT 下发 `thinking_to_answer` 事件（reasoning 与 content 天然分离，无需剥离）

#### Scenario: StubLLMClient 模拟 reasoning_content

- **GIVEN** TESTING=1 模式下使用 StubLLMClient
- **WHEN** chat_stream 流式输出
- **THEN** StubLLMClient SHALL 先输出 `reasoning_delta`（模拟思考），再输出 `text_delta`（模拟回答）
- **AND** 确保测试模式下思考横幅有确定性的 reasoning 内容可断言
