# ADR 0015: Langfuse Tracing 集成机制重写

**Status**: Accepted
**Date**: 2026-07-14

## Context

`docker-compose.yml` 已部署完整 Langfuse v3 栈（web + worker + ClickHouse + MinIO + Redis + Postgres），`project_rules.md` 明确要求"排查 bug 时…还要查看 Langfuse 的 trace"。但应用层集成存在两个根本缺陷：

1. **不产生嵌套结构**。[llm.py:127](../../src/finance_agent/llm.py) 和 [litellm_client.py:123](../../src/finance_agent/harness/litellm_client.py) 调用的是 `client.start_observation(as_type="generation", ...)`。Langfuse v4 文档明确：`start_observation` 是 manual observations API，"does **not** set the new observation as the active one in the OpenTelemetry context"——它不建立父子关系。结果是 5 层管线（4 分析师 -> 多空辩论 -> 交易员 -> 风险辩论 -> 基金经理）在 Langfuse 里塌成扁平的孤立 generation 列表，看不到拓扑。

2. **绕过 litellm 内置集成**。litellm 1.85.x 与 langfuse 4.x 多处不兼容（version 属性、sdk_integration 参数等），[llm.py:27-69](../../src/finance_agent/llm.py) 用 monkey-patch 把内置 LangFuseLogger 的方法全替成 no-op，然后自己写了 `_LangfuseCallback` 走 `start_observation`。这套补丁脆弱且仍受缺陷 1 影响。

拓扑是 LangGraph 静态 DAG（ADR-0011），并行扇出用 `Send()`（[routing.py:61-64](../../src/finance_agent/routing.py) 等 4 分析师 / 多空 / 3 风险辩论者）。ReAct Agent（ADR-0014）作为统一入口，5 层管线封装为 `run_deep_analysis` 流式工具。

trace 单元已定（见 CONTEXT.md "Trace" 条目）：**一次用户交互 = 一条 Trace**，深度分析与每次追问各为独立 Trace，同一 SQLite Session 的 N 条 Trace 通过 Langfuse `session_id` 聚合（option C，见 CONTEXT.md "Session" 与 Langfuse Session 的同名区分）。

## Decision

### 1. 双机制集成：CallbackHandler 管骨架 + `start_as_current_observation` 管 generation

**骨架层（图节点 span）用 LangChain CallbackHandler**：在 ReAct Agent 调用图的位置，`graph.ainvoke(..., config={"callbacks": [langfuse_handler]})`。LangGraph 的 `Send()` 扇出会自动把 callback 配置传播到每个并行节点，4 个分析师 / 多空 / 3 风险辩论者自动挂成正确的兄弟 span，无需手动处理 contextvar 传播。这一层白送 5 层拓扑，节点代码零改动。

**generation 层（LLM 调用细节）用 `start_as_current_observation`**：在 [llm.py](../../src/finance_agent/llm.py) 的 `call_llm` / `call_llm_stream` / `call_llm_with_tools` 三个入口内，用 `with langfuse.start_as_current_observation(as_type="generation", name=<model>, model=<model>, input=...) as gen:` 包裹 `litellm.completion` 调用，结束后 `gen.update(output=, usage_details=)`。因为这三函数在节点内运行、节点已被 CallbackHandler 挂在正确父级下，generation 自动归到对应 Agent span。Generation 附带 `prompt_name` + `prompt_version`（见 ADR-0016）。

### 2. ReAct 思考单独包 `react_loop` span

ReAct Agent 自身的 LLM 调用（思考/工具选择）用 `@observe(name="react_loop")` 包裹，使 trace 顶层结构为 `[react_loop] -> [search_stock] / [run_deep_analysis span -> 5 层...]`，而非扁平 generation 列表。这使 ADR-0010 关注的"Agent 行为可度量"（是否发起预期数量工具调用）在 trace 里可读。

### 3. 删除现有坏代码，不修补

删除 [llm.py:27-147](../../src/finance_agent/llm.py) 的 `_lf_noop` / `_lf_noop_init` / `_LangfuseCallback` 及其 callback 注册；删除 [litellm_client.py:120-236](../../src/finance_agent/harness/litellm_client.py) 的 `_langfuse` 初始化与 `start_observation` 调用。原因：这些代码用的是产生孤立 generation 的 `start_observation` API，修补它不如用正确的 `start_as_current_observation` 重写。litellm 内置 langfuse 集成保持 no-op 禁用状态（兼容性问题未解）。

### 4. trace 属性

调用边界处 `with propagate_attributes(session_id=<sqlite_session_id>, user_id=<user_id>):` 设置 trace 属性。`session_id` ≤200 字符（Langfuse 限制）。

## Alternatives Considered

- **I-1 全 `@observe` 装饰器**：给每个节点函数贴 `@observe`。依赖 LangGraph 传播 contextvar 到并行任务，无文档保证；且侵入 20+ 节点模块。否决。
- **I-2 节点内手动包 span**：每个节点函数体自己 `start_as_current_observation`。样板多，改动面大。部分采纳（仅 LLM 入口处用）。
- **I-4 state 传 trace_id**：把 `trace_id`/`span_id` 存进 `AnalysisState`，子节点手动认父。污染 state schema，违反 ADR-0011 的 state 纪律，干扰 Pydantic 序列化。否决。
- **litellm 内置 langfuse 集成**：litellm 1.85.x / langfuse 4.x 不兼容，需大量 monkey-patch。否决，保持禁用。

## Consequences

- **正**：5 层管线在 Langfuse 里完整可见为 span 树；LLM 调用的 prompt/output/usage/cost 挂在正确 Agent 下；trace 可读性支持 ADR-0010 的 Agent 行为度量。
- **负**：依赖 LangGraph `Send` 传播 callback 的行为（虽为 LangChain/LangGraph 原生路径，但非 Langfuse 文档显式承诺）。若未来 LangGraph 改并行调度机制需重新验证。
- **新增耦合**：`call_llm` 三入口对 Langfuse SDK 的依赖。但 Langfuse 仍可选（未配置 key 时跳过观测，与现状一致）。
- **litellm 内置集成永久禁用**：升级 litellm 后需重新评估是否解除禁用、改用官方集成。

## References

- [Langfuse Instrumentation - context manager vs manual observations](https://langfuse.com/docs/observability/sdk/instrumentation)
- [Langfuse Sessions - propagate session_id across traces](https://langfuse.com/docs/observability/features/sessions)
- [ADR-0010](0010-tool-use-refactor.md) - Agent 行为可度量的目标
- [ADR-0011](0011-five-layer-architecture.md) - 5 层管线拓扑与 state schema 纪律
- [ADR-0014](0014-agent-harness-orchestration.md) - ReAct Agent 作为统一入口、5 层管线封装为流式工具
- [llm.py:27-147](../../src/finance_agent/llm.py) - 待删除的坏集成代码
- [litellm_client.py:120-236](../../src/finance_agent/harness/litellm_client.py) - 待删除的坏集成代码
- [routing.py:61-64](../../src/finance_agent/routing.py) - `Send()` 并行扇出
- CONTEXT.md "Trace" / "Span" / "Generation" 条目
