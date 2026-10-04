# llm-provider-gateway Delta — add-kimi-reasoning-effort

## ADDED Requirements

### Requirement: kimi reasoning_effort 配置入口

系统 SHALL 为 Kimi 模型族（openai/ 前缀下 model 含 `kimi` 或 `k3` 前缀段）提供 reasoning_effort 的配置入口并透传到请求：支持档位 `none/low/high/max`（`none` SHALL 表示关闭思考，Kimi 官方语义为路由到无思考版）；请求参数 SHALL 经 `extra_body={"reasoning_effort": <值>}` 透传（litellm openai 路由拒收顶层 `reasoning_effort`，与 ark-glm 同机制）。系统 SHALL NOT 为 kimi 族设置隐式默认档位——未显式配置时不携带该参数，跟随端点模型默认。

#### Scenario: 请求级 effort=none 关思考
- **GIVEN** llm_config.model 为 `openai/kimi-for-coding` 且 provider_options 为 `{"reasoning_effort": "none"}`
- **THEN** 解析出的 profile provider_options SHALL 保留该值
- **AND** apply_provider_options SHALL 产出 `extra_body={"reasoning_effort": "none"}`

#### Scenario: 未配置时不携带
- **GIVEN** kimi 模型请求未提供 provider_options
- **THEN** 最终请求参数 SHALL 不含 reasoning_effort（不注入默认档）

#### Scenario: 非法值拒绝
- **WHEN** reasoning_effort 传入 `none/low/high/max` 之外的值（如 `medium`）
- **THEN** SHALL 显式抛错（pydantic ValidationError），不静默忽略

#### Scenario: k3 前缀模型同族识别
- **WHEN** model 为 `openai/k3` 或 `openai/k3-256k`
- **THEN** SHALL 识别为 kimi 族并走同一透传机制
