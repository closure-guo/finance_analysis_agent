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

### D4: 根 trace 记录 agent 产出（会话内容可见）

管线根 span（`deep_analysis:{股票}`）与 ReAct `react_loop` span 退出前，将 agent 产出写入 span 的 `output`，使 session/trace 层级直接可见 agent 输出（修复「session 只见 user input、output 恒 null」缺口）。

- **deep_analysis 根 span**：`_stream_graph` 捕获 `_root_obs = _root_cm.__enter__()` 的返回句柄；管线完成后（`accumulated` 就绪的一侧）`_root_obs.update(output=产出摘要)`。因根 span 创建于管线线程而 `accumulated` 由事件循环侧消费完成，采用「共享 sink 传递 obs 句柄 + Langfuse v4 按 observation id 更新（跨线程安全）」方案，实现期验证 `obs.update` 在 span 退出后的语义。
- **react_loop span**：同线程（事件循环），无并发问题——循环中追踪 agent 最终回复（`ActionType.TEXT`/ANSWER 事件内容），退出前 `_react_obs.update(output={"answer": 最终回复})`。
- output 内容：管线侧写各 agent 节点产出摘要 + 最终报告摘要；ReAct 侧写最终回复/总结。为防 trace 体积膨胀，output 放摘要级内容，不放完整报告原文。
- **理由**：这是原「会话内容」设计意图的落地——generation 级内容（#53）与 trace 级会话内容互补，缺一不可。

### D5: 优雅降级

`get_langfuse()` 返回 None 时不创建 observation；agent 为空退化为旧命名；session_id/stock_code 缺失省略对应 metadata 字段；`_root_obs`/`_react_obs` 缺失或更新失败时跳过（不阻断业务）。所有 Langfuse 调用沿用现有 try/except 模式，trace 故障不影响业务。

## Risks / Trade-offs

- [改动 4 处 LLM 入口签名，可能波及其它调用点] → 新参数均为可选（默认 `""`），现有调用零改动；用全量 `pytest` + `ruff` 回归。
- [Send 扇出并行节点的 agent 上下文错配] → agent 名靠显式传参（D1），不依赖 contextvar 传播，天然规避并行错配。
- [ReAct / harness 的 agent 语义与管线节点不同] → harness client 用固定回路级标签，与管线节点 agent 名区分，不强行复用节点名。
- [根 span output 跨线程更新：`obs.update` 在 span 退出后的 Langfuse v4 语义] → D4 实现期 task 0 验证（obs 按 id 更新队列 + flush 时序），失败则改在根 span 退出前由 output_provider 同步写入。
- [output 体积膨胀] → 只写摘要级内容（各 agent 产出摘要 + 报告摘要），不写完整报告原文。

## Migration Plan

纯新增可选参数 + 观测命名，无数据迁移、无 API 变更。直接全量；Langfuse 未配置环境（本地/CI stub）自动降级无影响。回滚 = revert 本 change。

## Open Questions

- 根 span output 的跨线程写入语义（D4 的 `obs.update` 在 span 退出后是否生效、flush 时序）——实现期 task 0 先验证，据结果定「共享 sink + id 更新」或「退出前 output_provider 同步写」。
- 管线侧 `accumulated` 中最终产出的确切字段清单（各 agent 摘要 key / final_report）——实现期按实际 state schema 定，控制 output 体积。
