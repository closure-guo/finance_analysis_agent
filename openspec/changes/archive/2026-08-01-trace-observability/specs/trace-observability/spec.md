## ADDED Requirements

### Requirement: 工具调用 span 可观测

ReAct Agent 执行工具调用时，系统 SHALL 在 Langfuse trace 中创建名为 `tool:{tool_name}` 的 span（as_type=span），记录工具调用的输入参数与输出结果，使其与 LLM generation span 在 trace 中分层可观测。

#### Scenario: 工具执行时创建 span

- **WHEN** ReAct Agent 在 [harness/loop.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py) 执行任一工具调用（如 web_search、search_stock、run_deep_analysis）
- **THEN** 系统 SHALL 在 Langfuse trace 中创建 `tool:{tool_name}` span，且 span 的 input 字段包含工具调用参数 args

#### Scenario: span 挂载到 react_loop 下

- **WHEN** 工具调用在 react_loop span 上下文内执行
- **THEN** 系统 SHALL 通过 contextvar 自动继承，使 `tool:{tool_name}` span 成为 `react_loop` span 的子 span，与同级的 LLM generation span 在 trace 树中并列

#### Scenario: span 记录 input 和 output

- **WHEN** 工具调用完成
- **THEN** 系统 SHALL 在 `tool:{tool_name}` span 的 input 字段记录工具参数 args，在 output 字段记录工具执行结果 result

### Requirement: 网络搜索 span 可观测

系统执行网络搜索时 SHALL 创建名为 `search_api_call` 的 span（as_type=span），记录搜索查询与结果数量，使其在 trace 中与上层调用（工具调用 span 或规则预搜索 span）分层可观测。

#### Scenario: 搜索执行时创建 span

- **WHEN** [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 的搜索函数被调用
- **THEN** 系统 SHALL 创建 `search_api_call` span，input 字段包含 query 与 max_results 参数

#### Scenario: 作为工具调用子 span

- **WHEN** 网络搜索作为 ReAct Agent 的工具调用被执行（上层为 `tool:web_search` span）
- **THEN** 系统 SHALL 通过 contextvar 自动继承，使 `search_api_call` span 成为 `tool:web_search` span 的子 span

#### Scenario: span 记录结果数量

- **WHEN** 网络搜索完成
- **THEN** 系统 SHALL 在 `search_api_call` span 的 output 字段记录返回结果数量 count

### Requirement: open_span helper 优雅降级

系统 SHALL 在 [langfuse_tracing.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/langfuse_tracing.py) 提供 `open_span(name, input)` 上下文管理器，封装 Langfuse span 创建逻辑，并在 Langfuse 未配置时优雅降级，确保 trace 故障不影响业务流程。

#### Scenario: Langfuse 已配置时创建 span

- **WHEN** Langfuse 已配置（`get_langfuse()` 返回有效客户端）且调用 `open_span(name="tool:web_search", input={"args": {...}})`
- **THEN** 系统 SHALL 调用 `start_as_current_observation(name=name, as_type="span", input=input)` 创建 span 并进入其上下文

#### Scenario: Langfuse 未配置时返回 nullcontext

- **WHEN** Langfuse 未配置（`get_langfuse()` 返回 None）且调用 `open_span(...)`
- **THEN** 系统 SHALL 返回 `contextlib.nullcontext()`，不抛出异常、不创建 span、不产生开销

#### Scenario: span 创建异常时降级不影响业务

- **WHEN** `start_as_current_observation` 抛出异常（如 Langfuse 服务不可达）
- **THEN** 系统 SHALL 捕获异常并降级为 nullcontext，确保业务流程继续执行，不因 trace 故障中断工具调用或搜索

### Requirement: span 不改变业务行为

span 的创建 SHALL 对业务行为透明——不改变 SSE 事件流、API 响应内容、工具执行结果，确保 trace 埋点是纯观测层操作。

#### Scenario: span 创建对 SSE 事件流透明

- **WHEN** 工具调用或网络搜索在 span 上下文内执行
- **THEN** 系统 SHALL 发布与无 span 时完全一致的 SSE 事件流（事件类型、顺序、内容不变）

#### Scenario: span 异常时业务结果不变

- **WHEN** span 创建或更新过程中发生异常
- **THEN** 系统 SHALL 仍返回正确的工具执行结果或搜索结果，业务输出不受 trace 故障影响
