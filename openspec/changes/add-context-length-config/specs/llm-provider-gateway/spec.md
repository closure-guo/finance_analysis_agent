## ADDED Requirements

### Requirement: 请求级上下文长度配置

用户 SHALL 能经前端设置页配置上下文长度（tokens），随请求级 `llm_config.contextLength` 下发；留空时跟随 registry 静态 `capability.max_context` 默认。resolver 解析 profile 时，请求级 `contextLength`（正整数）SHALL 覆盖 `capability.max_context`；环境变量 `LLM_MAX_CONTEXT`（正整数）SHALL 在无请求级值时覆盖默认。非法值（非正整数）MUST 显式报配置错误，不得静默忽略。覆盖后的 capability SHALL 经既有 `ContextBudget.from_capability` 链路驱动 ReAct 上下文预算。

#### Scenario: 请求级覆盖
- **WHEN** 请求级 llm_config 携带 contextLength=200000 且解析成功
- **THEN** profile.capability.max_context 为 200000，其余能力字段不变

#### Scenario: 环境变量覆盖
- **WHEN** 无请求级 contextLength 且 env LLM_MAX_CONTEXT=200000
- **THEN** 解析出的 profile capability.max_context 为 200000

#### Scenario: 非法值拒绝
- **WHEN** contextLength 为 0、负数或非整数
- **THEN** 显式配置错误（HTTP 422 或 resolver 配置异常），不静默回退

#### Scenario: 留空跟随默认
- **WHEN** 请求与环境均未配置 contextLength
- **THEN** capability.max_context 保持 registry 静态声明值，行为与现状一致
