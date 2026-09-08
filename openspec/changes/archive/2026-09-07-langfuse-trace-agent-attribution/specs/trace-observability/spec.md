# Delta Spec: trace-observability

## ADDED Requirements

### Requirement: trace 记录会话内容（根 span output）

系统 SHALL 在管线根 span（`deep_analysis:{股票}`）与 ReAct `react_loop` span 退出前，将 agent 产出写入 span 的 output，使 Langfuse trace/session 层级直接可见 agent 输出，而非仅有 user input。

#### Scenario: deep_analysis 根 span 记录 agent 产出

- **WHEN** 5 层分析管线完成（`deep_analysis:{股票}` 根 span 退出）
- **THEN** 系统 SHALL 将根 span 的 output 更新为管线产出摘要（各 agent 节点产出 + 最终报告摘要）

#### Scenario: react_loop span 记录 agent 最终回复

- **WHEN** ReAct Agent 完成一轮执行（`react_loop` span 退出）
- **THEN** 系统 SHALL 更新 `react_loop` span 的 output 为 agent 最终回复/总结

### Requirement: LLM generation 按子 agent 归因

系统 SHALL 在创建 LLM generation 观测时，以发起该调用的子 agent 名命名 observation（如 `technical_analyst`、`bull_debater`、`risk_judge`、`trader`、`fund_manager`)，使 Langfuse 观测列表可直接区分每次调用归属的子 agent。

#### Scenario: 管线节点 LLM 调用以 agent 名命名

- **WHEN** 管线节点（如 `technical_analyst`）经 `call_llm_streaming(node_name=...)` 触发 LLM 调用，且 Langfuse 已配置
- **THEN** 系统 SHALL 创建 name 为该 agent 名（`technical_analyst`）的 generation observation，而非 `litellm:{model}`

#### Scenario: agent 名透传至 observation

- **WHEN** 任一 LLM 入口（`call_llm` / `call_llm_stream` / `call_llm_with_tools` / harness LLM client）被调用且调用方提供 agent 名
- **THEN** 系统 SHALL 将该 agent 名用作 generation observation 的 name

### Requirement: agent 名缺省时向后兼容

当调用方未提供 agent 名时，系统 SHALL 将 LLM generation observation 命名为 `litellm:{model}`，与本改动前的现状一致，确保未接入 agent 归因的调用点行为不回归。

#### Scenario: 未传 agent 名退化为现状命名

- **WHEN** LLM 入口被调用但未提供 agent 名（或为空字符串）
- **THEN** 系统 SHALL 将该 generation observation 命名为 `litellm:{model}`

### Requirement: generation 携带过滤 metadata

系统 SHALL 在 LLM generation observation 的 metadata 中记录可用的过滤维度字段，包括 `agent`、分析会话 `session_id`、股票 `stock_code`，使 Langfuse 可按 agent 或一次分析运行过滤调用。任一字段在调用上下文不可得时 SHALL 省略该字段而不报错。

#### Scenario: 上下文字段写入 metadata

- **WHEN** 管线节点触发 LLM 调用，且调用上下文提供 session_id / stock_code
- **THEN** 系统 SHALL 在 generation 的 metadata 中记录 `agent`、`session_id`、`stock_code`

#### Scenario: 字段缺失时省略不报错

- **WHEN** 调用上下文中 session_id 或 stock_code 不可得
- **THEN** 系统 SHALL 省略对应 metadata 字段，正常完成观测创建，不抛出异常

### Requirement: 观测改动对业务透明

LLM generation 的命名与 metadata SHALL 为纯观测层操作，不改变 SSE 事件流、API 响应内容、LLM 的输入 prompt 或输出内容；Langfuse 未配置时系统 SHALL 不创建观测、不影响业务流程。

#### Scenario: Langfuse 未配置时零影响

- **WHEN** Langfuse 未配置（`get_langfuse()` 返回 None）
- **THEN** 系统 SHALL 跳过 observation 创建，LLM 调用与业务流程正常执行

#### Scenario: 观测埋点不改变 LLM 内容

- **WHEN** LLM 调用附带 agent 命名 / metadata
- **THEN** 系统 SHALL 发送与无埋点时完全一致的 prompt，且返回内容不变
