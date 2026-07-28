## Context

当前 `ThinkingBanner` 组件（`frontend/src/App.tsx`）在两种模式下已通过共用的 `handleChatStreamEvent` 统一处理思考事件（`thinking_token` / `thinking_replace` / `thinking_to_answer`），流式时自动展开并显示"正在思考"，完成时固定显示"已深度思考 · {N} 字"。

存在两个问题：
1. **完成态信息密度低**：折叠状态下用户只能看到"已深度思考 · N 字"，无法判断本轮思考的主题，必须展开才能决定是否关注。
2. **缺乏结构化标题**：思考内容本身可能是长文本，完成后没有标题摘要，可读性差。

本变更引入基于信息密度的标题生成策略，让 LLM 在输出思考时按策略决定是否带标题，前端解析提取标题用于横幅折叠态展示与下拉框置顶加粗。

### 现有实现关键点

- `ThinkingBanner({ content, streaming })`：流式时 `expanded=true`（`useState(true)` + useEffect），完成态标题文案 `streaming ? '正在思考' : isJustFinished ? '已深度思考' : '思考过程'`
- `UIMessage.thinkingContent?: string`，无标题字段
- 思考完成判定：`streaming={!!msg.streaming && !msg.chatResponse}`（出现回答即视为思考完成）
- 内容渲染：`<p className="whitespace-pre-wrap">{content}</p>` 纯文本，未走 Markdown 渲染

## Goals / Non-Goals

**Goals:**

- 统一快速模式与深度模式澄清阶段在用户输入 query 或工具调用（tool call）后的思考流式展示
- 思考进行中横幅显示"思考中"，可点击展开/折叠，展开后下拉框实时显示流式思考内容
- 思考完成后根据 query 与思考内容判断是否生成标题并展示
- 横幅完成态四态展示规则：折叠×（有/无标题）、展开×（有/无标题）
- 引入标题生成策略 prompt，LLM 按信息密度/逻辑复杂度决定输出 `##` 标题 / `**加粗**` 分段 / 无标题
- 思考内容（正文与标题）与对话内容一样持久化，切换会话或关闭页面后可恢复

**Non-Goals:**

- 不改动深度分析管线 UI（`Pipeline Thinking Display`）的思考展示逻辑--管线阶段思考仍在管线区域展示，本变更仅覆盖对话流（快速模式 + 深度模式澄清阶段）
- 不改动后端 SSE 事件类型（不新增 `thinking_done` 等事件），标题由前端解析思考内容获得
- 不改动 `thinking_to_answer` 将回答移至回答区的现有逻辑
- 不在后端 `chat_history` 中冗余存储 `thinkingTitle` 字段（标题是 `thinking` 内容的派生信息，前端恢复时复用 `extractThinkingTitle` 解析即可）
- 不改动搜索横幅、工具调用横幅

## Decisions

### 决策 1：标题由 LLM 按策略在思考输出中生成，前端解析提取（非后端独立生成）

**选择**：将标题生成策略 prompt 嵌入 LLM 的思考输出环节，LLM 按策略决定思考内容是否以 `##` 标题分层；前端在思考完成时解析 `thinkingContent` 的 Markdown，提取首个 `## ` 标题作为横幅展示标题。

**理由**：
- 用户给出的 prompt（"在输出前，评估回复的信息密度和逻辑复杂度…"）是面向 LLM 输出格式的指令，天然适合嵌入思考输出环节
- 无需新增后端事件或额外 LLM 调用，零额外延迟与成本
- `##` 标题既服务于下拉框内的思考内容可读性（分层展示），又能被前端提取复用为横幅标题，一物两用
- `**加粗**` 分段与"无标题"策略自然映射为横幅"无标题"分支（显示"思考已完成"），符合需求

**替代方案**：
- 后端在思考完成后额外调用 LLM 生成标题 -> 否决，增加一次 LLM 调用延迟与成本，且思考内容已含足够信息
- 后端新增 `thinking_done` 事件携带 title 字段 -> 否决，需改后端 SSE 协议与事件下发，改动面大；且标题本质是思考内容的派生信息，前端解析即可

### 决策 2：标题提取规则--仅识别 `## ` 层级标题

**选择**：前端在思考完成时（`streaming` 由 true 变 false，或 `thinking_to_answer` 处理后）扫描 `thinkingContent`，提取首个 `^##\s+(.+)$` 行的标题文本作为 `thinkingTitle`；若无匹配，`thinkingTitle` 为 undefined。

**理由**：
- 与策略 prompt 对齐："用 `##` 标题分层" -> 提取为横幅标题；"用 `**加粗**` 分段"与"不用标题" -> 横幅无标题
- `##` 是 Markdown 二级标题，语义明确，解析简单（一行正则）
- `**加粗**` 是段落级强调，不具备标题语义，不作为横幅标题

**替代方案**：同时识别 `**加粗**` 作为标题 -> 否决，`**加粗**` 在策略中明确"不用层级标题"，作为横幅标题会违背策略语义且造成下拉框内重复展示

### 决策 3：横幅状态模型--新增 `thinkingTitle` 字段，ThinkingBanner 接收 `title` prop

**选择**：
- `UIMessage` 新增 `thinkingTitle?: string`
- 思考完成时由事件处理器写入 `thinkingTitle`（解析 `thinkingContent` 得到）
- `ThinkingBanner` 新增 `title?: string` prop，完成态展示规则按下表：

| 完成态横幅 | 有标题 | 无标题 |
|-----------|--------|--------|
| 折叠（expanded=false） | 显示 `title` | 显示"思考已完成" |
| 展开（expanded=true） | 显示"思考已完成"，下拉框内标题加粗置顶 | 显示"思考已完成"，下拉框无置顶标题 |

**思考中态**：横幅显示"思考中"（脉冲动画），不论折叠/展开。

**理由**：
- 折叠态显示标题让用户不展开即可获知思考主题，是本变更核心价值
- 展开态横幅固定"思考已完成"，避免横幅标题与下拉框内标题重复（下拉框内已加粗置顶展示标题）
- 下拉框内标题加粗置顶 = 在 `thinkingContent` 渲染前，将提取出的标题以加粗样式单独渲染一行，其后渲染思考正文（思考正文中的 `##` 标题保留原样，由 Markdown 渲染分层）

### 决策 4：思考中默认展开，保持现有"流式自动展开"行为

**选择**：思考进行中（`streaming=true`）横幅默认展开，实时滚动显示流式思考内容；用户可手动折叠；完成后保持当前展开/折叠状态不变。

**理由**：
- 与现有 `Thinking Banner Display` 规范"流式思考自动展开"一致，最小化行为变更
- "该横幅可点击展开"描述的是横幅的交互能力（折叠后可再展开），非默认折叠
- 流式时折叠会导致用户看不到实时思考，与"流式输出展示"目的相悖

**替代方案**：思考中默认折叠，仅显示"思考中"，点击才展开 -> 否决，违背现有规范且降低流式可见性

### 决策 5：下拉框内容改用 Markdown 渲染（支持 `##` 标题与 `**加粗**`）

**选择**：`ThinkingBanner` 下拉框内容区域由现有 `<p className="whitespace-pre-wrap">{content}</p>` 改为 `ReactMarkdown` 渲染（与助手回答区一致的渲染配置），以正确展示 `##` 层级标题与 `**加粗**` 分段。

**理由**：
- 策略 prompt 要求 LLM 输出 `##` 标题分层与 `**加粗**` 分段，纯文本渲染会原样显示 Markdown 标记，失去分层意义
- 助手回答区已用 `ReactMarkdown + remarkGfm`，复用同一渲染配置保证一致性

### 决策 6：标题生成策略 prompt 嵌入后端思考输出环节

**选择**：在后端 ReAct Agent Harness 的思考输出 prompt 中嵌入用户给出的标题生成策略：

```
在输出前，评估回复的信息密度和逻辑复杂度：
- 若包含多要点、需对比分类、或用户处于决策场景 -> 用 ## 标题分层
- 若仅为单一事实、简短确认、日常寒暄 -> 直接输出，不用标题
- 长度 >150 字但主题单一 -> 用 **加粗** 分段，不用层级标题
核心原则：标题服务于可读性，不为形式而形式。
```

**理由**：策略本质是 LLM 输出格式决策，嵌入思考输出 prompt 让 LLM 在生成思考内容时即按策略输出，前端只需解析。后端仅需在思考 prompt 模板中追加这段策略，改动最小。

### 决策 7：思考标题持久化策略--前端恢复时复用解析逻辑，不后端冗余存储

**选择**：思考正文已由后端 `append_chat(thinking=...)` 持久化到 `chat_history`（`session_store.py` 第 407-408 行）。思考标题（`thinkingTitle`）不在后端冗余存储，而是在前端历史会话恢复时，复用 `extractThinkingTitle` 从已持久化的 `thinking` 内容解析获得，与实时流式完成时使用完全相同的解析逻辑。

**理由**：
- 标题是思考内容的派生信息（提取首个 `##` 行），存储到后端会造成冗余，且实时流与历史恢复两套逻辑需同步维护
- 复用同一 `extractThinkingTitle` 函数保证实时流与历史恢复行为一致（DRY）
- 零后端改动：`append_chat` 已支持 `thinking` 参数，`ChatHistoryEntry.thinking` 字段已存在，前端 `selectSession` 已读取 `h.thinking`
- 满足"切换会话或关闭页面后可恢复"需求：思考正文从后端 `chat_history` 恢复，标题从正文解析恢复

**替代方案**：
- 后端 `append_chat` 新增 `thinking_title` 参数，存入 `chat_history` entry -> 否决，标题是派生信息，存储冗余；且需改后端 `ReplyCollector`、`append_chat` 签名、`session_store.py` schema、前端 `ChatHistoryEntry` 类型，改动面大
- 历史会话恢复时不解析标题，按"思考已完成"展示 -> 否决，违背"与对话内容一样持久化恢复"需求，历史会话思考横幅将永远无标题

## Risks / Trade-offs

- **[LLM 标题输出不稳定]** LLM 可能不严格遵循策略，该用标题时未用、或不该用时用了 -> 可接受，横幅无标题时回退显示"思考已完成"，不影响功能；可通过 Langfuse trace 观察命中率后优化 prompt
- **[历史会话标题解析一致性]** 历史会话恢复时复用 `extractThinkingTitle` 解析，与实时流使用相同逻辑，保证一致；若历史 thinking 内容不含 `##` 标题（策略未生效时的旧数据），则无标题按"思考已完成"展示 -> 可接受，符合策略语义
- **[下拉框 Markdown 渲染性能]** 流式时每 token 触发 Markdown 重渲染 -> 可接受，思考内容通常较短；若性能问题可考虑节流，但属实现细节
- **[标题与正文重复]** 下拉框内"标题加粗置顶" + 正文 Markdown 渲染保留 `##` 标题，可能视觉重复 -> 设计为：置顶标题为横幅展示用加粗行，正文保留 `##` 原样渲染分层，二者语义不同（置顶=横幅标题摘要，正文 `##`=内容分层），可接受；若体验不佳可在正文渲染时剥离首个 `##` 标题行

## Migration Plan

- 后端：在思考输出 prompt 模板追加标题生成策略段落（2 处改动：`prompts/quick_mode.md` + `prompts/deep_mode.md`，两种模式各自加载）
- 前端：
  - `UIMessage` 新增 `thinkingTitle?: string`
  - `handleChatStreamEvent` 在思考完成判定时（`thinking_to_answer` 处理后、`chat_done` 时）解析 `thinkingContent` 提取标题写入 `thinkingTitle`
  - `ThinkingBanner` 新增 `title?: string` prop，重写完成态横幅文案与下拉框置顶标题渲染
  - 下拉框内容改用 `ReactMarkdown` 渲染
- 历史会话恢复：`selectSession` 构建 `UIMessage` 时，复用 `extractThinkingTitle(h.thinking)` 解析标题写入 `thinkingTitle`，与实时流保持一致（思考正文已由后端 `chat_history.thinking` 持久化，无需后端改动）
- 回滚：还原后端 prompt 段落 + 前端 `ThinkingBanner` 与 `UIMessage` 改动即可

## Open Questions

- 思考完成判定时机：当前以 `streaming` 由 true 变 false 判定，但一轮对话中可能多次思考（多轮 ReAct）。需确认 `thinkingTitle` 是每轮覆盖（仅保留最后一轮标题）还是每轮累积。倾向：每轮覆盖，`thinkingTitle` 反映最近一轮思考主题。具体在 tasks 实现阶段结合 `thinking_to_answer` 时序确认。
- 标题语言：策略 prompt 未限定语言，LLM 可能中英混用。是否需在 prompt 中限定"标题用中文"？倾向：不限定，与 query 语言一致即可。
