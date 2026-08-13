# Design: langfuse-trace-agent-attribution

## Context

Langfuse 的 LLM generation 观测在 `llm.py` 三入口（`call_llm`、`call_llm_stream`、`call_llm_with_tools`）与 `harness/litellm_client.py` 创建，`name` 统一为 `litellm:{model}`。子 agent 名在调用点是现成的：管线节点用 `call_llm_streaming(..., node_name="technical_analyst")` 硬编码传入（`nodes/analysts.py` 等 9 处），但 `call_llm_streaming` 未把 `node_name` 继续传给 `call_llm_stream`，只用于前端 thinking 横幅。trace 父子树由已并入 main 的 content-fidelity 改动（手动 root span + CallbackHandler callbacks）维持，本改动不触碰该结构，仅改 generation 命名与 metadata。

## Goals / Non-Goals

**Goals:**
- Langfuse 中每个 LLM generation 以子 agent 名命名，列表可直接区分调用归属。
- generation 携带 `agent` / `session_id` / `stock_code` metadata，可按维度过滤。
- 向后兼容：agent 缺省时退化为现状命名；Langfuse 未配置时零影响。

**Non-Goals:**
- 不重建 root span / session 聚合 / trace 内容记录（content-fidelity 已实现）。
- 不改变 SSE 事件流、API 响应、LLM 输入/输出内容。
- 不引入新的 Langfuse 依赖或升级 SDK。

## Decisions

### D1: agent 名通过显式参数透传（而非 contextvar / 调用栈推断）

给 `call_llm` / `call_llm_stream` / `call_llm_with_tools` / harness `LiteLLMClient` 增加可选参数 `agent: str = ""`，调用点显式传入。
- 管线节点：`call_llm_streaming(node_name=X)` → 内部 `call_llm_stream(..., agent=X)`。
- 其余 `call_llm` / `call_llm_with_tools` 调用点（约 6 处）从所在节点补对应 agent 名。
- harness ReAct client：agent 固定为 ReAct 回路所属 agent 标签。
- **理由**：agent 名在调用点已硬编码存在，显式传参最直接、可测试。**备选**：用 contextvar 在节点边界注入自动继承——引入隐式全局态，Send 扇出下需小心传播正确性，调试成本高，否决。

### D2: observation `name` 用纯 agent 名，缺省退化 `litellm:{model}`

`name = agent if agent else f"litellm:{model}"`。
- **理由**：模型名 Langfuse 已有独立 model 字段/列，重复进 name 冗余且拉长。**备选** `{agent} · {model}`：便于一眼看模型，但冗余，否决。
- 纯观测命名，不影响任何业务字段。

### D3: metadata 携带 agent / session_id / stock_code

generation 的 metadata 增加三字段，供 Langfuse 按维度过滤，无需解析 name。
- **理由**：过滤是用户排查的实际动作（按 agent 看某类调用、按 session 看一次运行）。
- session_id / stock_code 从节点 `state` 读取（`state.get("session_id")` / `state.get("stock_code")`）；缺省时省略该字段，不报错。
- **现状注记**：「按 session 过滤」有待未来调用方传入 `session_id`——当前管线节点 state 无 `session_id` 键，故今日管线 generation 上仅预期 `agent` / `stock_code`。

### D4: 优雅降级

`get_langfuse()` 返回 None 时不创建 observation；agent 为空退化为旧命名；session_id/stock_code 缺失省略对应 metadata 字段。所有 Langfuse 调用沿用现有 try/except 模式，trace 故障不影响业务。

## Risks / Trade-offs

- [改动 4 处 LLM 入口签名，可能波及其它调用点] → 新参数均为可选（默认 `""`），现有调用零改动；用全量 `pytest` + `ruff` 回归。
- [Send 扇出并行节点的 agent 上下文错配] → agent 名靠显式传参（D1），不依赖 contextvar 传播，天然规避并行错配。
- [ReAct / harness 的 agent 语义与管线节点不同] → harness client 用固定回路级标签，与管线节点 agent 名区分，不强行复用节点名。

## Migration Plan

纯新增可选参数 + 观测命名，无数据迁移、无 API 变更。直接全量；Langfuse 未配置环境（本地/CI stub）自动降级无影响。回滚 = revert 本 change。

## Open Questions

- 无（实现期按 D3 从节点 `state` 取 session_id/stock_code；若 `state` 缺失对应字段则省略，不影响本 delta 核心目标）。
