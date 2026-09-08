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
- **THEN** 若事件对应 `web_search` / `batch_web_search` 工具，SHALL NOT 附加到任何工具调用记录、SHALL NOT 新建记录
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

## REMOVED Requirements

### Requirement: thinking_to_answer 将回答移至回答区

**Reason**: 开启 DeepSeek 原生思考模式后，`reasoning_content` 与 `content` 天然分离，不再需要将思考内容剥离为回答。原生 reasoning 直接作为思考展示，content 直接作为回答展示。

**Migration**: 前端移除 `thinking_to_answer` 事件处理逻辑（`handleChatStreamEvent` 中的 `thinking_to_answer` case）。思考横幅直接消费 `thinking_token`（来源为 reasoning_content），回答区直接消费 `chat_token`（来源为 content），无需转换。
