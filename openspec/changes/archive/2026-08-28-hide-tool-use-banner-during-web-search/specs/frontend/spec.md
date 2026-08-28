## MODIFIED Requirements

### Requirement: Conversation Stream Common Events

系统 SHALL 在深度模式的澄清阶段和快速模式中共用同一套对话流事件处理逻辑，包括 thinking、tool_call、chat 和 error 类事件。搜索类工具（`web_search` / `batch_web_search`）的调用与结果 SHALL NOT 进入工具调用横幅，仅由独立搜索横幅承载。

#### Scenario: thinking_token 累积思考内容

- **GIVEN** 对话流进行中
- **WHEN** 收到 thinking_token 事件
- **THEN** token 追加到助手消息的 thinkingContent

#### Scenario: thinking_replace 替换思考内容

- **GIVEN** 对话流进行中，助手消息已有 thinkingContent
- **WHEN** 收到 thinking_replace 事件
- **THEN** thinkingContent 整体替换为事件中的 token（用于 DSML 清理等后处理）

#### Scenario: thinking_to_answer 将回答移至回答区

- **GIVEN** 对话流进行中，文本已作为 thinking_token 流式输出
- **WHEN** 收到 thinking_to_answer 事件
- **THEN** 将 thinkingContent 末尾与 answer 匹配的部分移至 chatResponse
- **AND** thinkingContent 保留剩余部分（思考轨迹），避免回答重复

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
- **WHEN** 收到 chat_token 事件
- **THEN** token 追加到助手消息的 chatResponse

#### Scenario: chat_done 结束流式

- **GIVEN** 对话流进行中，助手消息 streaming=true
- **WHEN** 收到 chat_done 事件
- **THEN** 助手消息 streaming 设为 false

#### Scenario: 对话流 error 事件

- **GIVEN** 对话流进行中
- **WHEN** 收到 error 事件
- **THEN** 助手消息 chatResponse 设为"❌ {message}"，streaming 设为 false

## ADDED Requirements

### Requirement: Search Tool Banner Exclusivity

系统 SHALL 将搜索类工具（`web_search` / `batch_web_search`）的调用展示与工具调用横幅互斥，搜索类工具的状态与结果仅由独立搜索横幅（SearchBanner）承载，避免同一搜索行为同时出现两个横幅造成信息重复。

#### Scenario: 仅搜索类工具调用时只显示搜索横幅

- **GIVEN** 对话流进行中，助手消息本轮仅调用了 `web_search` / `batch_web_search` 工具
- **WHEN** 收到 `search_start` 事件
- **THEN** 助手消息渲染搜索横幅（searchStatus 为 'searching'）
- **AND** 助手消息的 toolCalls 列表为空，SHALL NOT 渲染工具调用横幅

#### Scenario: 搜索类与非搜索类工具并存时两个横幅各司其职

- **GIVEN** 对话流进行中，助手消息本轮既调用了 `search_stock` 又调用了 `web_search`
- **WHEN** 事件处理完成
- **THEN** `search_stock` 记录在 toolCalls 列表，渲染工具调用横幅
- **AND** `web_search` 的状态与结果由搜索横幅展示，SHALL NOT 出现在工具调用横幅中
- **AND** 两个横幅并存，各自承载不同语义，无信息重复

#### Scenario: 搜索横幅完成态不回填工具调用横幅

- **GIVEN** 助手消息的 searchStatus 已为 'done'（搜索横幅展示"搜索了 N 个网页"）
- **WHEN** 渲染助手消息
- **THEN** 工具调用横幅中 SHALL NOT 出现 `web_search` / `batch_web_search` 条目
- **AND** 搜索结果仅展示在搜索横幅的可折叠列表中

## MODIFIED Requirements

### Requirement: Chat History Restore With Tool Calls

系统 SHALL 在加载已有会话时，从 chat_history 恢复助手消息的 thinking 内容和 tool_calls 记录。恢复时 SHALL 过滤搜索类工具（`web_search` / `batch_web_search`），这些工具的历史记录不还原到工具调用横幅。

#### Scenario: 恢复工具调用记录

- **GIVEN** 加载的会话 chat_history 中某条助手消息包含 tool_calls
- **WHEN** 构建助手消息
- **THEN** 将 tool_calls 中 name 不为 `web_search` / `batch_web_search` 的条目映射为 ToolCallEntry 列表（含 name、args、result_text、done）
- **AND** name 为 `web_search` / `batch_web_search` 的条目 SHALL NOT 还原到 toolCalls 列表
- **AND** 仅当过滤后的 ToolCallEntry 列表非空时，在助手消息中展示工具调用横幅

#### Scenario: 恢复思考内容

- **GIVEN** 加载的会话 chat_history 中某条助手消息包含 thinking 字段
- **WHEN** 构建助手消息
- **THEN** 将 thinking 内容设为助手消息的 thinkingContent
- **AND** 在助手消息中展示思考横幅（已完成状态）
