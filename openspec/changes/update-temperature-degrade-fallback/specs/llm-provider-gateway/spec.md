# Delta for llm-provider-gateway

## ADDED Requirements

### Requirement: temperature 拒绝自动降级

adapter raw 入口（raw_completion / raw_stream / raw_acompletion）SHALL 支持温度拒绝自动降级：请求携带 `temperature` 且端点以 temperature 相关错误拒绝（如思考型模型的 `invalid temperature: only 1 is allowed for this model`）时，剔除 `temperature` 后重试一次（走端点默认值）。降级 SHALL 记录 logger warning 并经 `update_current_span` 写 trace（`degradation=temperature_dropped_endpoint_rejected`）；重试仍失败 SHALL 按原有错误归一上抛，MUST NOT 无限重试；未携带 temperature 的请求 MUST NOT 触发本降级。

#### Scenario: 思考型模型温度拒绝降级成功

- **GIVEN** 请求携带 `temperature=0.3` 且模型端点仅允许 temperature=1
- **WHEN** 端点返回 400 `invalid temperature: only 1 is allowed for this model`
- **THEN** adapter 剔除 `temperature` 后重发一次并正常返回结果
- **AND** trace 记录 `degradation=temperature_dropped_endpoint_rejected`，logger 记 warning

#### Scenario: 降级后仍失败按原错误上抛

- **WHEN** 剔除 temperature 重试后仍失败（如认证错误）
- **THEN** 按归一化错误上抛，不再重试

#### Scenario: 非 temperature 错误不触发降级

- **WHEN** 端点错误信息不含 temperature（如 auth / model_not_found）
- **THEN** 不剔除参数、不重试，走原有错误路径

#### Scenario: 未携带 temperature 的请求不受影响

- **WHEN** 请求未携带 `temperature`（如 capability probe、probe 探测调用）
- **THEN** 本降级逻辑零介入，行为与现状一致
