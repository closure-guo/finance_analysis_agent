## Why

当前 ReAct Agent 的工具调用（[loop.py:497-512](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py#L497-L512)）与网络搜索（[web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py)）在 Langfuse trace 中是黑盒——这两处零 Langfuse 埋点，所有信息堆在 react_loop 的单一 span 里，无法区分「LLM 回复 / 工具调用 / 网络搜索」三类操作。调试 Bug 时无法在 trace 上定位「是工具层的锅还是搜索层的锅」，只能去代码里 grep 半天。

本 delta 补齐工具调用 span 与网络搜索 span，让 trace 分层可观测，与现有 LLM generation span、管线节点 span 共同构成完整的可观测性分层。

## What Changes

- 新增 `trace-observability` capability，定义工具调用 span 与网络搜索 span 的规范（命名、as_type、input/output 字段、父子关系）。
- [harness/loop.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py) 工具执行处补 `tool:{name}` span（as_type=span，挂到 react_loop span 下）。
- [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 搜索执行处补 `search_api_call` span（as_type=span，作为 tool:web_search 或规则预搜索 span 的子 span）。
- [langfuse_tracing.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/langfuse_tracing.py) 新增 `open_span(name, input)` 上下文管理器 helper，封装 `start_as_current_observation` + 未配置 Langfuse 时的优雅降级（返回 nullcontext）。
- 不改 SSE 事件流、不改前端、不改现有 capability 的 spec 行为。

## Capabilities

### New Capabilities

- `trace-observability`: ReAct 工具调用与网络搜索的 Langfuse trace span 规范，定义 span 命名、字段、父子挂载关系与优雅降级要求。

### Modified Capabilities

无。本 delta 是纯 trace 层补埋点，不改变任何现有 capability 的 spec 行为（事件流、前端、会话、E2E 均不变）。

## Impact

- **代码**：[langfuse_tracing.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/langfuse_tracing.py)（新增 helper）、[harness/loop.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py)（工具执行处补 span）、[web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py)（搜索执行处补 span）。
- **可观测性**：Langfuse trace 结构增强，新增 `tool:{name}` 与 `search_api_call` 两类 span；现有 LLM generation span、管线节点 span 不受影响。
- **API/事件流**：无变更，对前端透明。
- **依赖**：无新增依赖，复用现有 Langfuse SDK。
- **风险**：低。纯观测层补埋点，未配置 Langfuse 时通过 `open_span` 优雅降级跳过 span 创建，不影响业务流程。
