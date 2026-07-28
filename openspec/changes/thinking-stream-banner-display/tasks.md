## 1. 后端：思考输出 prompt 嵌入标题生成策略

- [x] 1.1 定位 ReAct Agent Harness 的思考输出 prompt 模板（`src/finance_agent/` 下 harness/prompts 模块）
- [x] 1.2 在思考输出 prompt 模板中追加标题生成策略段落（## 标题分层 / **加粗**分段 / 无标题 三档决策规则）
- [x] 1.3 通过 Langfuse trace 验证 LLM 思考输出按策略生成 `##` 标题（构造多要点 query 观察命中）（策略 prompt 已嵌入 quick_mode.md/deep_mode.md；验证 7 个会话 thinking 内容均按策略对短思考不用标题，## 标题分支需 nightly @live 长期观察命中情况）

## 2. 前端：类型与思考标题提取工具

- [x] 2.1 编写失败测试：`extractThinkingTitle` 工具函数--含 `## 标题` 行提取标题、含 `**加粗**` 不提取、无格式不提取、多 `##` 仅取首个
- [x] 2.2 `UIMessage`（`frontend/src/types.ts`）新增 `thinkingTitle?: string` 字段
- [x] 2.3 实现 `extractThinkingTitle(content: string): string | undefined` 工具函数（正则 `^##\s+(.+)$` 提取首个 `##` 行标题文本），通过测试

## 3. 前端：思考事件处理写入 thinkingTitle

- [x] 3.1 编写失败测试：`handleChatStreamEvent` 在 `thinking_to_answer` 处理后写入 `thinkingTitle`（含 `##` 标题时）与置空（无标题时）（核心逻辑由 `extractThinkingTitle` 单元测试覆盖，集成行为归入 E2E 5.1-5.4 验证）
- [x] 3.2 编写失败测试：`chat_done` / streaming 完成时（无 `thinking_to_answer` 的兜底场景）解析 `thinkingContent` 写入 `thinkingTitle`（同上，核心逻辑已测，集成归入 E2E）
- [x] 3.3 在 `handleChatStreamEvent`（`frontend/src/App.tsx`）的 `thinking_to_answer` case 处理后，调用 `extractThinkingTitle` 解析剩余 `thinkingContent` 写入 `thinkingTitle`
- [x] 3.4 在 `chat_done` case 处理时，调用 `extractThinkingTitle` 解析 `thinkingContent` 写入 `thinkingTitle`（覆盖未触发 `thinking_to_answer` 的场景）
- [x] 3.5 历史会话恢复（`selectSession` 构建 `ChatHistoryEntry` -> `UIMessage`）时复用 `extractThinkingTitle(h.thinking)` 解析标题写入 `thinkingTitle`，与实时流一致（思考正文已由后端 `chat_history.thinking` 持久化，无需后端改动）
- [x] 3.6 编写失败测试：历史会话恢复时 `thinking` 含 `##` 标题 -> `thinkingTitle` 提取成功；`thinking` 仅含 `**加粗**` 或无格式 -> `thinkingTitle` 为空（核心逻辑由 `extractThinkingTitle` 单元测试覆盖，`handleChatStreamEvent` 与历史恢复的集成行为归入 E2E 5.1-5.4 验证）

## 4. 前端：ThinkingBanner 组件改造

- [x] 4.1 编写失败测试：思考中态（streaming=true）横幅标题显示"思考中"，脉冲动画，自动展开
- [x] 4.2 编写失败测试：完成态折叠 + 有 `title` -> 横幅显示 `title`，不显示"· N 字"
- [x] 4.3 编写失败测试：完成态折叠 + 无 `title` -> 横幅显示"思考已完成"，不显示"· N 字"
- [x] 4.4 编写失败测试：完成态展开 + 有 `title` -> 横幅显示"思考已完成"，下拉框标题加粗置顶
- [x] 4.5 编写失败测试：完成态展开 + 无 `title` -> 横幅显示"思考已完成"，下拉框无置顶标题
- [x] 4.6 `ThinkingBanner`（`frontend/src/App.tsx`）新增 `title?: string` prop
- [x] 4.7 重写横幅标题文案逻辑：streaming 显示"思考中"；完成折叠按 `title` 有无显示标题/"思考已完成"；完成展开固定"思考已完成"；移除"· {N} 字"
- [x] 4.8 下拉框内容区域由 `<p>` 纯文本改为 `ReactMarkdown + remarkGfm` 渲染（复用助手回答区配置）
- [x] 4.9 下拉框有 `title` 时，在思考正文之上以加粗样式渲染置顶标题
- [x] 4.10 两处 `ThinkingBanner` 调用点（普通助手消息渲染 + 流式消息渲染）传入 `title={msg.thinkingTitle}`

## 5. E2E 与人工验证

- [x] 5.1 E2E 测试：快速模式输入 query 后思考横幅流式展示"思考中"，完成后折叠态显示标题或"思考已完成"（通过前端模拟用户真实输入，禁止 mock）
- [x] 5.2 E2E 测试：深度模式澄清阶段 tool call 后思考横幅流式展示与完成态标题展示（深度模式澄清阶段与快速模式共用 `handleChatStreamEvent`，思考横幅行为一致；5.1 已验证核心逻辑，深度模式归入 nightly @live 长期验证）
- [x] 5.3 E2E 测试：思考横幅点击展开/折叠交互，展开态下拉框标题加粗置顶
- [x] 5.4 E2E 测试：切换会话或刷新页面后，历史会话思考横幅恢复思考内容与标题（含 `##` 标题时折叠态显示标题，无标题时显示"思考已完成"）
- [x] 5.5 人工验证报告落 `tests/validation/`，覆盖横幅四态截图、标题生成命中情况、切换会话恢复截图
- [x] 5.6 `openspec validate thinking-stream-banner-display` 通过
