## ADDED Requirements

### Requirement: 前端能力矩阵展示

设置页 SHALL 展示当前 profile 的能力矩阵（non_stream/stream/tool_call/tool_followup/json_output），数据来自 `/api/llm-config/test` 返回的 probe 结果；probe 未完成时先显示静态 capability，完成后更新。
(Previously: 后端端点已返回 capability 矩阵，前端未消费。)

#### Scenario: probe 结果驱动矩阵
- **WHEN** 设置页完成一次连通性测试
- **THEN** 能力矩阵按 probe 事实渲染（逐项通过/失败态可区分）

### Requirement: 模式入口按 capability 门禁

前端 SHALL 按 capability 禁用不满足要求的模式入口并显示原因：`tool_call=false` 的 profile 禁用深度 ReAct（提示可切换 profile 或使用快速模式）；管线结构化入口在 `json_output=false` 时禁用。门禁 SHALL 消费 probe 事实（probe 优先于静态声明）。被禁用入口 MUST 显示禁用原因，不得静默隐藏。
(Previously: 任意 profile 均可进入任意模式，弱能力 provider 在深度模式下故障。)

#### Scenario: 无工具能力禁用深度模式
- **GIVEN** 当前 profile probe 事实 tool_call=false
- **WHEN** 用户尝试进入深度 ReAct 模式
- **THEN** 入口呈禁用态并显示「该 provider 不支持工具调用」及可行动建议

#### Scenario: probe 修正静态声明
- **GIVEN** 静态 capability 声明 tools!=none 但 probe 事实 tool_call=false
- **WHEN** 渲染模式入口
- **THEN** 门禁按 probe 事实（false）判定，而非静态声明
