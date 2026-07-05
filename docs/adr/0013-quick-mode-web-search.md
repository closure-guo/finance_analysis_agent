# ADR 0013: Quick Mode — Single Tool Call + Tavily Web Search

**Status**: Accepted
**Date**: 2026-07-05

## Context

CONTEXT.md 的双模式设计原定快速模式为 v2.0，使用 ReAct 循环 + tool calling。现在需要提前实现快速模式，为前端"快速模式"按钮提供后端支持。

快速模式的核心矛盾：用户需要秒级响应（对标 DeepSeek 快速模式 2 秒出结果），但纯 LLM 知识有时效性限制（不知道最新财报、新闻）。需要一种机制在"速度"和"信息新鲜度"之间取平衡。

## Decision

### 1. 单次工具调用，非 ReAct 循环

快速模式最多发起 1 次工具调用（web search），不使用多轮 ReAct 循环。

**否决 ReAct 的理由**：
- ReAct 循环工具调用次数不可控（可能 3-5 次），响应时间无上限
- 单次调用有确定性上界：LLM 决策 ~2s + 搜索 ~2s + LLM 生成 ~3s = ~7s
- DeepSeek API 原生支持 `tools` + `tool_choice="auto"`，不需要 `create_agent` 框架
- 实现：`call_llm` 加 `tools=[web_search_tool]`，如果 `finish_reason="tool_calls"` 执行一次搜索，把结果塞回 messages 再调一次 LLM

**与 CONTEXT.md 的变更**：原"ReAct 循环"改为"单次工具调用（非 ReAct）"。

### 2. Tavily 作为 web search 提供商

**否决其他选项的理由**：
- DuckDuckGo：免费但结果质量差，可能被限流
- SerpAPI：免费额度太少（100 次/月）
- AKShare 新闻：仅覆盖个股新闻，东方财富 API 不稳定
- Tavily：专为 AI 设计，返回结构化结果（title + url + content），1000 次/月免费

**API key 管理**：与 DeepSeek key 同模式——HF Spaces Secrets 存 `TAVILY_API_KEY`，代码通过 `os.environ.get("TAVILY_API_KEY")` 读取，不硬编码。

### 3. LLM 自主决定搜索 query

工具 schema 的 `query` 参数由 LLM 自主生成。LLM 根据用户问题构造搜索词（如"贵州茅台 2026年 最新财报"），后端不干预。

**否决固定模板的理由**：用户问题多样（"茅台毛利率""茅台和五粮液对比"），固定模板无法覆盖。LLM 构造的 query 更贴合问题意图。

### 4. Kimi 风格搜索横幅

前端展示可折叠搜索横幅（类 Kimi）：
- 搜索中：显示"正在搜索：{query}"
- 搜索完成：显示"搜索了 N 个网页"，点击展开显示网页列表（标题 + URL + 摘要）
- 无搜索：不显示横幅

SSE 事件流：
```
{"type": "search_start", "query": "贵州茅台 最新财报"}
{"type": "search_result", "results": [{"title": "...", "url": "...", "content": "..."}], "count": 5}
{"type": "chat_token", "token": "..."}  // 流式回答
{"type": "chat_done"}
```

### 5. 引用标注 [1][2]

LLM prompt 要求在回答中用 `[1][2]` 标注引用来源，对应搜索结果的序号。前端将 `[1]` 渲染为可点击链接，点击后展开搜索横幅中对应的网页。

### 6. Tavily 不可用时降级

- **无 API key**：不传 tools 参数给 LLM，纯 LLM 回答，横幅显示"搜索不可用，基于已有知识回答"
- **搜索失败**：把失败信息作为 tool result 返回给 LLM，LLM 基于自身知识回答，横幅显示"搜索失败"
- **LLM 不调工具**：LLM 认为自身知识够用，直接流式回答，不显示横幅

## Consequences

- **新增依赖**：`tavily-python` 包（Tavily 官方 SDK）
- **`llm.py` 改动**：`call_llm` 和 `call_llm_stream` 新增 `tools` 参数支持，处理 `tool_calls` 响应
- **`api.py` 改动**：`/api/chat` 端点增加 tool calling 逻辑——第一次 LLM 调用带 tools，如触发 tool call 则执行 Tavily 搜索，第二次 LLM 调用带搜索结果流式输出
- **前端改动**：`App.tsx` 新增搜索横幅组件（可折叠），处理 `search_start` / `search_result` SSE 事件，渲染引用标注 `[1]` 为可点击链接
- **CONTEXT.md 更新**：快速模式从 ❌ v2.0 改为 ✅ v1.1；Tavily 从 ❌ v2.0 改为 ✅ v1.1；新增 Quick Mode 术语
- **ADR-0010 关系**：ADR-0010 Step 1 的 tool calling 设计"保留给快速模式"——本 ADR 是其落地，但不使用 `create_agent` 框架，直接用 litellm 的 `tools` 参数

## References

- [ADR-0010](0010-tool-use-refactor.md) — tool calling 设计基础（Step 1 已撤销，保留给快速模式）
- [ADR-0011](0011-five-layer-architecture.md) — 深度模式不需要 tool calling 的决策
- [Tavily API 文档](https://docs.tavily.com) — AI 搜索 API
- [DeepSeek Function Calling](https://platform.deepseek.com/docs/function_calling) — tools 参数支持
