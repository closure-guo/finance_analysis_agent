# ADR 0014: Adopt Agent Harness as Unified Orchestration Layer

**Status**: Accepted
**Date**: 2026-07-07

## Context

当前系统有两种编排路径：深度模式走 LangGraph 静态 DAG（5 层管线），快速模式走两步 LLM 调用（单次工具调用，非 ReAct）。ADR-0013 明确否决了 ReAct 用于快速模式，理由是"循环次数不可控，响应时间无上限"。

现引入 Agent Harness（mini_harness），一个基于 Claude Code 设计的简化 ReAct 循环框架。目标：用 ReAct Agent 统一编排三种模式（深度/快速/追问），将 5 层管线封装为流式工具。

## Decision

### 1. 采用 mini_harness ReAct 循环作为统一编排层

ReAct Agent 作为所有用户交互的统一入口。三种模式不再走不同代码路径，而是通过 Agent 配置参数区分：

| 模式 | 工具集 | max_iterations | system prompt |
|------|--------|---------------|---------------|
| 深度模式 | search_stock, run_deep_analysis, web_search | 10 | 引导调用深度分析 |
| 快速模式 | web_search | 3 | 引导简洁回答，不暴露深度分析工具 |
| 追问模式 | web_search | 3 | 注入报告上下文，不暴露深度分析工具 |

**对 ADR-0013 的部分推翻**：快速模式现在使用 ReAct 循环。延迟控制从"不做 ReAct"变为"限制 max_iterations=3 + 不暴露深度分析工具"。max_iterations=3 给了硬性上界：最多 3 次 LLM 调用 + 3 次工具调用。快速模式不暴露 run_deep_analysis 工具，从 schema 层面杜绝意外触发 90 秒管线。

**对 ADR-0011 的影响**：5 层管线拓扑不变，仍然是 LangGraph 静态 DAG。变化的是外部编排：从 API 层直接调用 LangGraph 变为 ReAct Agent 通过工具调用间接触发 LangGraph。

### 2. 流式工具接口

扩展 mini_harness 的工具接口，支持流式返回。工具函数从 `execute() -> ToolResult` 扩展为 `execute_stream() -> AsyncIterator[StreamEvent]`。

- 普通工具（web_search, search_stock）：yield 一次 TOOL_RESULT
- 流式工具（run_deep_analysis）：yield 多个 PROGRESS 事件（管线节点进度）+ 最终 TOOL_RESULT

新增 `ActionType.PROGRESS` 事件类型，用于管线节点进度推送。所有事件走单一 SSE 通道，Agent 是唯一编排点。

### 3. ToolResult.metadata 携带结构化数据

`ToolResult` 新增 `metadata: dict | None` 字段。`output` 是 LLM 可见的文本（Markdown 报告），`metadata` 是不进入 LLM 上下文的结构化数据（chart_data, analyst_reports 等）。

API 层在 Agent 的 SSE 事件流中拦截 `TOOL_METADATA` 事件，调用 `session_store.create_session()` 持久化。mini_harness 保持纯粹，不依赖 session_store。

### 4. 工具参数混合注入

`run_deep_analysis` 的 schema 只暴露 `stock_code` 和 `stock_name`（LLM 从对话推断）。`analysis_type`、`peer_codes`、`enable_web_search` 等前端 UI 收集的配置通过闭包注入，不暴露给 LLM。

### 5. 追问机制

追问是新的 ReAct 对话（非延续），从 SQLite session 恢复上下文：报告 Markdown 前 6000 字符 + analyst_summaries + chat_history，注入 Agent 的初始 context。追问模式不暴露 run_deep_analysis。

### 6. API 层保持两个端点

`/api/analyze`（深度模式）和 `/api/chat`（快速模式 + 追问）保持不变，内部共享 `build_agent(mode=...)` 工厂函数。API 层负责：构建 Agent、拦截 TOOL_METADATA 持久化 session、SSE 事件映射。

### 7. 跳过权限系统

所有工具都是只读、无副作用的。不采用 mini_harness 的 deny-first 权限系统，所有工具 auto_approve。权限系统留到未来引入有副作用的工具时再启用。

### 8. System Prompt 设计

遵循 Claude Code 的 8 段结构（Identity -> Safety -> Tone -> Workflow -> Tool Policy -> Domain Knowledge -> Environment -> Reminders）。利用 U 型注意力曲线：安全规则放头部（IMPORTANT 标记），关键操作规则放底部重申。不写刚性流程图，信任模型自主决策执行顺序。

## Consequences

- **ADR-0013 部分推翻**：快速模式从"单次工具调用，非 ReAct"变为"ReAct，max_iterations=3"。延迟上界从 ~7s 放宽到 ~15s（3 轮迭代），换取 Agent 自主决策能力。
- **ADR-0011 不变**：5 层管线拓扑仍是 LangGraph 静态 DAG，只是外部触发方式从直接调用变为工具调用。
- **react_agent.py 废弃**：现有深度模式的 stock 解析 ReAct 循环被 mini_harness 替代。
- **新增依赖**：mini_harness 作为项目内模块引入，需要适配 DeepSeek/Kimi API。
- **前端 SSE 事件适配**：新增 `progress` 和 `tool_metadata` 事件类型处理。
