## Context

当前系统的 Langfuse trace 适配已覆盖三层（ADR-0015）：

- **LLM generation span**：[harness/litellm_client.py:114-248](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py#L114-L248) 用 `start_as_current_observation(as_type="generation")` 观测每次 LLM 调用。
- **管线节点 span**：[agent_factory.py:620-637](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py#L620-L637) + [api.py:727-739](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L727-L739) 注入 LangChain CallbackHandler，5 层 LangGraph 节点自动挂成 span 树。
- **ReAct loop span**：[agent_factory.py:892-921](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py#L892-L921) 的 `react_loop` span + `propagate_attributes(user_id)`。

但 ReAct Agent 的工具调用与网络搜索是黑盒：

- [harness/loop.py:497-512](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py#L497-L512) 工具执行处零 Langfuse 埋点。
- [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 搜索执行处零 Langfuse 埋点。

所有信息堆在 `react_loop` 单一 span 里，无法区分「LLM 回复 / 工具调用 / 网络搜索」三类操作。

## Goals / Non-Goals

**Goals:**

- 工具调用在 Langfuse trace 中有独立 `tool:{name}` span，记录 args 与 result。
- 网络搜索在 Langfuse trace 中有独立 `search_api_call` span，记录 query 与结果数量。
- 提供 `open_span(name, input)` 上下文管理器 helper，统一封装 span 创建与优雅降级。
- 不改 SSE 事件流、不改前端、不改现有 capability 的 spec 行为。

**Non-Goals:**

- 不补规则层 span（`rule_preprocessing` / `pre_search`）——属于 Delta 1 `transparent-system-events` 的范围。
- 不补管线节点内数据获取 span（[fetch.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/nodes/fetch.py) akshare 调用、[compute.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/nodes/compute.py) 指标计算）——留给后续独立 delta。
- 不改 SSE 事件类型、不改前端 UI——属于 Delta 1 的范围。
- 不改现有 LLM generation span、管线节点 span 的行为。

## Decisions

### 决策 1：`open_span` helper 放 [langfuse_tracing.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/langfuse_tracing.py)，而非新建模块

**选择**：放在现有 `langfuse_tracing.py`。

**理由**：该模块已提供 `get_langfuse()` 单例与 `get_callback_handler()`，是 Langfuse 适配的统一入口。`open_span` 复用 `get_langfuse()`，天然继承优雅降级逻辑。Delta 1 的规则层 span 也会复用同一 helper，放公共模块避免重复。

**备选**：新建 `src/finance_agent/trace.py`。否决——会产生与 `langfuse_tracing.py` 职责重叠的模块，违反单一职责。

### 决策 2：span 用 `as_type="span"`，不是 `"generation"`

**选择**：`as_type="span"`。

**理由**：工具调用和网络搜索不是 LLM 调用，用 `generation` 会在 Langfuse UI 里误归类为 LLM 调用，混淆 token 统计与成本。`span` 是通用观测类型，符合语义。

### 决策 3：工具 span 挂 `react_loop` span 下（contextvar 继承）

**选择**：依赖 Langfuse contextvar 自动继承，工具 span 在 `react_loop` span 上下文内创建，自动挂为其子 span。

**理由**：[harness/litellm_client.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py) 的 generation span 已验证此模式可行。工具调用发生在 react_loop 内部，contextvar 上下文天然存在，无需手动指定父 span。

**备选**：手动传 parent span 引用。否决——contextvar 已自动处理，手动传参会增加耦合且易出错。

### 决策 4：搜索 span 作为调用方的子 span，不固定父 span

**选择**：`search_api_call` span 在 [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 内创建，父 span 由调用方上下文决定——LLM 工具调用时挂 `tool:web_search` 下，规则触发时挂 `pre_search` 下（Delta 1）。

**理由**：web_search 有两个调用路径（ReAct 工具调用 + 规则预搜索），搜索 span 不应硬编码父 span，由 contextvar 上下文自动决定，保持调用方无关。

### 决策 5：优雅降级用 `contextlib.nullcontext`

**选择**：未配置 Langfuse（`get_langfuse()` 返回 None）时，`open_span` 返回 `contextlib.nullcontext()`。

**理由**：标准库（符合「优先使用 Python 标准库」规范），零开销，业务代码无感知。与 [harness/litellm_client.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py) 现有的降级模式一致。

## Risks / Trade-offs

- **[contextvar 传播失败导致 span 挂错位置]** → 复用 `start_as_current_observation` 模式（litellm_client 已验证可行）；E2E 验证 trace 结构时检查父子关系。
- **[span 创建增加延迟]** → `open_span` 仅记录元数据（name/input），不阻塞业务；未配置 Langfuse 时 `nullcontext` 零开销；已配置时 span 创建是异步批量上报，对请求延迟影响可忽略（<1ms）。
- **[与 Delta 1 共享 `open_span` helper 的耦合]** → helper 放公共模块 `langfuse_tracing.py`，本 delta 先引入 helper（ADDED），Delta 1 archive 时直接使用，无 spec 冲突。两个 delta 独立 archive 顺序无关。
- **[span 异常影响业务流程]** → `open_span` 内部 try/except 包裹 span 创建，异常时降级为 nullcontext，确保业务流程不受 trace 故障影响。
