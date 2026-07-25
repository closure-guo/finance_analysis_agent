# Proposal: add-search-banner

## Why

CONTEXT.md 描述了"类 Kimi 搜索横幅"交互：

> 搜索中显示"正在搜索：{query}"，搜索完成后显示"搜索了 N 个网页"，点击展开显示网页列表（标题 + URL + 摘要）

但前端实际实现中：
- `SearchBanner` 组件在 `App.tsx:1543` 定义但**全项目无引用**（死代码）
- 快速模式：`searchStatus`/`searchResults`/`searchQuery` 被设置到 UIMessage 上，但 `MessageRenderer` 的 chat 分支未渲染这些字段，用户看不到搜索状态和结果
- 深度模式：搜索结果通过 `attachToolResult` 附加到 ToolCallBanner，仅显示"找到 N 条结果：{前3条标题}"摘要，无独立搜索横幅

这导致用户在快速模式下完全看不到搜索过程，在深度模式下搜索结果被折叠为工具调用的一行摘要，与 Kimi 的可展开搜索横幅体验差距明显。

## What

1. **快速模式**：在 `MessageRenderer` 的 chat 分支中渲染 `SearchBanner` 组件，展示搜索状态（searching/done/error）和可展开的搜索结果列表
2. **深度模式澄清阶段**：将 `search_result` 事件从 `attachToolResult`（ToolCallBanner 摘要）改为独立搜索横幅展示，与快速模式保持一致
3. **搜索中状态**：收到 `search_start` 事件时显示"正在搜索：{query}"，脉冲动画
4. **搜索完成状态**：收到 `search_result` 事件时显示"搜索了 N 个网页"，可展开查看网页列表（标题 + URL + 摘要 + favicon）

## Impact

| 文件 | 改动 |
|------|------|
| `frontend/src/App.tsx` - MessageRenderer | chat 分支添加 SearchBanner 渲染条件 |
| `frontend/src/App.tsx` - SearchBanner 组件 | 适配 searchStatus/searchResults/searchQuery 数据结构，支持 searching/done/error 三态 |
| `frontend/src/App.tsx` - startAnalysis（深度模式） | search_result 事件改为设置 searchStatus/searchResults 而非 attachToolResult |

不涉及后端改动，SSE 事件类型和数据结构不变。
