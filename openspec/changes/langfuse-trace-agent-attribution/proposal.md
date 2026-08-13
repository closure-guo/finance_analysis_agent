# Proposal: langfuse-trace-agent-attribution

## Why

Langfuse 观测中所有 LLM generation 的 `name` 均为 `litellm:{model}`，无法区分某次调用属于哪个子 agent（`technical_analyst` / `bull_debater` / `risk_judge` / `trader` …）。在 trace 列表按 agent 定位调用（如核对某分析师 prompt/输出）时，只能在几十条同名记录里逐条点开辨认。

> 背景：`feat/agent-trace-content-fidelity`（PR #53，已并入 main）已实现 root span + session 聚合、reasoning/tool_calls 落 generation output、prompt 元数据等观测闭环主体。**本 delta 仅补其缺口：generation 按子 agent 命名 + 过滤 metadata**，不重复已落地内容。

## What Changes

- LLM generation observation 以**子 agent 名**命名（如 `technical_analyst`、`bull_debater`),agent 名在调用点透传至 `llm.py` 三入口与 harness LLM client。
- generation metadata 增加 `agent` / `session_id` / `stock_code`，支持按 agent、按一次分析运行过滤。
- **向后兼容**：agent 名为空时，observation 名退化为现状 `litellm:{model}`。
- 纯观测层改动：不改变 SSE 事件流、API 响应、LLM 输入输出内容。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `trace-observability`: 新增「LLM generation 按子 agent 归因」需求，并约定 agent 名缺省时的向后兼容降级。

## Impact

- **代码**:
  - `src/finance_agent/llm.py` — `call_llm` / `call_llm_stream` / `call_llm_with_tools` 三入口的 observation 命名与 metadata。
  - `src/finance_agent/harness/litellm_client.py` — ReAct 回路的 generation 命名。
  - `src/finance_agent/nodes/_llm_utils.py` — `call_llm_streaming` 透传 `node_name` 至 `call_llm_stream`。
  - 其余 `call_llm` / `call_llm_with_tools` 调用点（`nodes/*`)按节点定义补 agent 名。
- **观测系统**: Langfuse（generation 命名、metadata）；不升级 SDK、不改 trace 树结构。
- **行为**: SSE / API / LLM 内容不变；Langfuse 未配置时零影响。
- **契约**: `openspec/specs/trace-observability/spec.md` 经 delta 修改。
