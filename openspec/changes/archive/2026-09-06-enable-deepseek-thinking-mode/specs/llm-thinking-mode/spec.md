## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Conversation Stream Common Events

系统 SHALL 在深度模式的澄清阶段和快速模式中共用同一套对话流事件处理逻辑。思考内容来源于 DeepSeek 原生 `reasoning_content`（通过 `thinking_token` 事件下发），与回答内容（`chat_token` 事件）天然分离，不再使用 `thinking_to_answer` 剥离机制。搜索类工具（`web_search` / `batch_web_search`）的调用与结果 SHALL NOT 进入工具调用横幅，仅由独立搜索横幅承载。

#### Scenario: thinking_token 累积原生思考内容

- **GIVEN** 对话流进行中
- **WHEN** 收到 thinking_token 事件（来源为 LLM 原生 reasoning_content）
- **THEN** token 追加到助手消息的 thinkingContent
- **AND** thinkingContent 是独立的思维链，与 chatResponse（content）分离

#### Scenario: thinking_to_answer 事件不再下发

- **GIVEN** 对话流进行中，LLM 输出 reasoning_content 后输出 content
- **WHEN** 思考与回答流式下发完成
- **THEN** SHALL NOT 收到 thinking_to_answer 事件（reasoning 与 content 天然分离）
- **AND** 前端无需执行思考剥离为回答的逻辑

#### Scenario: thinking_replace 事件不再下发

- **GIVEN** 对话流进行中
- **WHEN** LLM 原生 reasoning_content 流式输出
- **THEN** SHALL NOT 收到 thinking_replace 事件（原生 reasoning 无需 DSML 清理后处理）
- **AND** 思考内容直接流式展示，无需覆盖

#### Scenario: tool_call 记录到工具调用横幅

- **GIVEN** 对话流进行中
- **WHEN** 收到 tool_call 事件，且 name 不为 `run_deep_analysis`、`web_search`、`batch_web_search`
- **THEN** 创建 ToolCallEntry（含图标、标签、参数摘要、done=false）追加到助手消息的 toolCalls 列表
- **AND** 工具调用与思考过程分离展示

#### Scenario: 搜索类 tool_call 不进入工具调用横幅

- **GIVEN** 对话流进行中
- **WHEN** 收到 tool_call 事件，且 name 为 `web_search` 或 `batch_web_search`
- **THEN** SHALL NOT 在助手消息的 toolCalls 列表中创建 ToolCallEntry
- **AND** 该工具的状态与结果由 `search_start` / `search_result` 事件驱动搜索横幅展示
- **AND** 不触发管线 UI

#### Scenario: tool_result 附加到对应工具调用

- **GIVEN** 对话流进行中，助手消息已有工具调用记录
- **WHEN** 收到 tool_result 事件
- **THEN** 若事件对应 `web_search` / `batch_web_search` 工具，SHALL NOT 附加到任何工具调用记录、SHALL NOT 新建记录（其结果由 `search_result` 事件驱动搜索横幅展示）
- **AND** 否则，优先附加到同名且未完成的最近一次工具调用记录
- **AND** 若无同名未完成记录，回退到最近未完成的任意工具调用
- **AND** 若该记录已完成（已被 search_result/stock_resolved 等结构化事件先行附加），跳过避免重复
- **AND** 若无任何匹配记录且结果非空，新建一条仅含结果的工具调用记录

#### Scenario: chat_token 累积回答

- **GIVEN** 对话流进行中
- **WHEN** 收到 chat_token 事件（来源为 LLM content，与 reasoning 分离）
- **THEN** token 追加到助手消息的 chatResponse

#### Scenario: chat_done 结束流式

- **GIVEN** 对话流进行中，助手消息 streaming=true
- **WHEN** 收到 chat_done 事件
- **THEN** 助手消息 streaming 设为 false

#### Scenario: 对话流 error 事件

- **GIVEN** 对话流进行中
- **WHEN** 收到 error 事件
- **THEN** 助手消息 chatResponse 设为"❌ {message}"，streaming 设为 false
