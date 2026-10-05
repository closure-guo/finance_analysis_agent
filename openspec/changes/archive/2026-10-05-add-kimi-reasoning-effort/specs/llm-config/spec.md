# llm-config Delta — add-kimi-reasoning-effort

## ADDED Requirements

### Requirement: Kimi 族请求级 provider_options 白名单与 judge effort 配置

resolver 请求级分支 SHALL 为 Kimi 模型族登记 provider_options 白名单 `REQUEST_OVERRIDABLE["kimi"] = {"reasoning_effort"}`，校验经 registry `KimiOptions` schema（`none/low/high/max`，extra=forbid）；白名单外的 key SHALL 显式报错。评估裁判 SHALL 支持环境变量 `JUDGE_REASONING_EFFORT`：非空时并入请求级 llm_config.provider_options 透传，未设置时 SHALL NOT 携带该键（跟随端点默认档）。

#### Scenario: 请求级白名单校验
- **GIVEN** llm_config.model 为 `openai/kimi-for-coding` 且 provider_options 为 `{"reasoning_effort": "none"}`
- **THEN** resolve_profile SHALL 返回携带该 provider_options 的 profile

#### Scenario: 白名单外 key 显式报错
- **WHEN** kimi 模型请求级 provider_options 含 `{"thinking": "enabled"}`
- **THEN** SHALL 抛 IncompleteLLMConfigError（键不在白名单）

#### Scenario: judge effort 环境变量生效
- **GIVEN** 环境变量 `JUDGE_REASONING_EFFORT=none`
- **WHEN** judges 构建裁判请求
- **THEN** llm_config.provider_options SHALL 为 `{"reasoning_effort": "none"}`

#### Scenario: judge effort 未设置不带键
- **GIVEN** 环境变量 `JUDGE_REASONING_EFFORT` 未设置
- **THEN** judges 构建的 llm_config SHALL 不含 provider_options 键
