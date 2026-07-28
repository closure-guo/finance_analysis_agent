## MODIFIED Requirements

### Requirement: Thinking Banner Display

系统 SHALL 在助手消息中展示可折叠的思考过程横幅，统一覆盖快速模式与深度模式澄清阶段：用户输入 query 或工具调用（tool call）后，思考内容以流式输出展示。思考进行中横幅显示"思考中"；思考完成后根据是否生成标题（`thinkingTitle`）按横幅展开/折叠状态分别展示。

#### Scenario: 两种模式在 query 或 tool call 后流式展示思考

- **GIVEN** 快速模式或深度模式澄清阶段的对话流进行中
- **WHEN** 用户发送 query，或助手发起 tool call 后收到 `thinking_token` 事件
- **THEN** 助手消息渲染思考横幅，以流式输出展示思考内容
- **AND** 快速模式与深度模式澄清阶段共用同一套思考展示逻辑

#### Scenario: 思考中横幅展示与流式自动展开

- **GIVEN** 助手消息 streaming=true 且有 thinkingContent
- **THEN** 思考横幅自动展开，显示脉冲动画
- **AND** 横幅标题显示"思考中"
- **AND** 下拉框实时显示流式输出的思考内容，内容区域自动滚动到底部

#### Scenario: 思考完成折叠态有标题

- **GIVEN** 助手消息 streaming 从 true 变为 false，且 `thinkingTitle` 非空
- **AND** 思考横幅处于折叠状态（expanded=false）
- **THEN** 脉冲动画停止，显示勾选图标
- **AND** 横幅标题显示 `thinkingTitle` 的内容
- **AND** 不显示"· {N} 字"字数信息

#### Scenario: 思考完成折叠态无标题

- **GIVEN** 助手消息 streaming 从 true 变为 false，且 `thinkingTitle` 为空
- **AND** 思考横幅处于折叠状态（expanded=false）
- **THEN** 脉冲动画停止，显示勾选图标
- **AND** 横幅标题显示"思考已完成"
- **AND** 不显示"· {N} 字"字数信息

#### Scenario: 思考完成展开态横幅固定文案

- **GIVEN** 助手消息 streaming 从 true 变为 false
- **AND** 思考横幅处于展开状态（expanded=true）
- **THEN** 横幅标题显示"思考已完成"（不论是否有标题）
- **AND** 下拉框内思考内容若存在 `thinkingTitle`，SHALL 将标题以加粗样式置顶展示于思考正文之上
- **AND** 下拉框内思考正文按 Markdown 渲染（支持 `##` 层级标题与 `**加粗**` 分段）

#### Scenario: 思考完成展开态无标题

- **GIVEN** 助手消息 streaming 从 true 变为 false，且 `thinkingTitle` 为空
- **AND** 思考横幅处于展开状态（expanded=true）
- **THEN** 横幅标题显示"思考已完成"
- **AND** 下拉框内不渲染置顶标题，直接展示思考正文 Markdown

#### Scenario: 手动折叠/展开

- **GIVEN** 思考横幅已渲染
- **WHEN** 用户点击横幅标题
- **THEN** 切换展开/折叠状态
- **AND** 折叠时内容区域高度为 0，展开时最大高度 240px
- **AND** 折叠/展开后横幅标题按上述完成态规则刷新（折叠态按标题有无显示标题或"思考已完成"，展开态固定"思考已完成"）

## ADDED Requirements

### Requirement: Thinking Title Generation Strategy

系统 SHALL 在 LLM 思考输出环节嵌入标题生成策略，使 LLM 根据回复的信息密度和逻辑复杂度决定思考内容的输出格式；前端 SHALL 在思考完成时解析思考内容提取首个 `##` 层级标题作为思考横幅的展示标题。

#### Scenario: 嵌入标题生成策略 prompt

- **GIVEN** LLM 思考输出环节的 prompt 模板
- **THEN** SHALL 包含如下标题生成策略指令：
  - 若包含多要点、需对比分类、或用户处于决策场景 -> 用 `##` 标题分层
  - 若仅为单一事实、简短确认、日常寒暄 -> 直接输出，不用标题
  - 长度 >150 字但主题单一 -> 用 `**加粗**` 分段，不用层级标题
  - 核心原则：标题服务于可读性，不为形式而形式

#### Scenario: 前端提取 ## 标题作为思考标题

- **GIVEN** 助手消息思考完成（streaming 由 true 变 false，或 `thinking_to_answer` 处理后）
- **WHEN** `thinkingContent` 包含至少一个 `## ` 起始的行
- **THEN** 提取首个 `## ` 行的标题文本作为 `thinkingTitle` 写入助手消息
- **AND** `thinkingTitle` 用于思考横幅折叠态标题展示与展开态下拉框置顶加粗

#### Scenario: 无 ## 标题时思考标题为空

- **GIVEN** 助手消息思考完成
- **WHEN** `thinkingContent` 不包含 `## ` 层级标题行（仅含 `**加粗**` 分段或无格式）
- **THEN** `thinkingTitle` 设为空
- **AND** 思考横幅折叠态显示"思考已完成"，展开态下拉框不渲染置顶标题

#### Scenario: 历史会话恢复解析思考标题

- **GIVEN** 加载已有会话，从 chat_history 恢复助手消息的 thinking 内容
- **WHEN** 构建助手消息
- **THEN** 复用 `extractThinkingTitle` 从已持久化的 `thinking` 内容解析标题写入 `thinkingTitle`
- **AND** 与实时流式完成时使用相同的解析逻辑，保证行为一致
- **AND** 若 thinking 内容含 `##` 标题，思考横幅折叠态显示标题、展开态下拉框标题加粗置顶
- **AND** 若 thinking 内容无 `##` 标题，思考横幅按无标题规则展示（折叠态显示"思考已完成"，展开态下拉框无置顶标题）
