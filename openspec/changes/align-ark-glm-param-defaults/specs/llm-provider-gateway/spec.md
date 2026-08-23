# Delta for LLM Provider Gateway

## ADDED Requirements

### Requirement: ark-glm 输出预算对齐官方默认

系统 SHALL 将 ark-glm（方舟 GLM-5.3）的默认输出预算对齐官方默认值：max_tokens 默认 65536（官方默认，最大 131072，建议 ≥1024）。deep 长 JSON 节点（analyst/debate/trader/fund_manager）在默认预算下 SHALL 避免因 reasoning 与正文共享配额而触发 `finish_reason=length` 空正文中断。模型输出完整后自然 `stop`，预算仅为上限非固定消耗。

#### Scenario: 默认预算生效

- **GIVEN** 经 env 或 preset 解析到 ark-glm profile
- **WHEN** derive_output_budget 派生预算且调用方未显式传 max_tokens
- **THEN** 预算 SHALL 为 65536（命令式：等于 registry max_output 与 default_params.max_tokens）

#### Scenario: 显式传 max_tokens 覆盖

- **WHEN** 调用方显式传 max_tokens（如 `_build_focus_summary` 的 400）
- **THEN** 显式值 SHALL 优先（derive_output_budget requested 分支）

### Requirement: ark-glm reasoning_effort 显式配置入口

系统 SHALL 为 ark-glm 提供 reasoning_effort 的配置入口并透传到请求：官方默认 `max`；支持档位 `max/high/low`（GLM-5.3 范围）；配置来源按优先级：请求级 llm_config → 环境变量 `LLM_REASONING_EFFORT` → registry 默认 `max`。透传的 `reasoning_effort` SHALL 出现在发给端点的请求参数中（OpenAI 兼容端点透传）。

#### Scenario: env 配置生效

- **GIVEN** 环境变量 `LLM_REASONING_EFFORT=high` 且模型为方舟 GLM（`glm` in model）
- **THEN** 解析出的 profile provider_options SHALL 含 `reasoning_effort: "high"`
- **AND** apply_provider_options SHALL 产出请求参数 `reasoning_effort="high"`

#### Scenario: 默认值生效

- **GIVEN** 未配置 LLM_REASONING_EFFORT 且模型为方舟 GLM
- **THEN** provider_options SHALL 含 `reasoning_effort: "max"`（官方默认）

#### Scenario: 请求级覆盖

- **GIVEN** llm_config 提供 `reasoning_effort: "low"`
- **THEN** 最终请求参数 SHALL 为 `reasoning_effort="low"`（请求级 > env > 默认）

#### Scenario: 非法值拒绝

- **WHEN** reasoning_effort 传入非 `max/high/low` 值
- **THEN** SHALL 显式抛错（pydantic ValidationError / 等价），不静默忽略