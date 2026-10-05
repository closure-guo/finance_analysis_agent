# Delta for llm-config

## MODIFIED Requirements

### Requirement: 连通性测试

系统 SHALL 提供连通性测试功能，用户在保存配置前可验证 LLM 配置是否有效。测试请求 SHALL 由后端发送探测 LLM 请求验证，返回成功/失败结果及错误分类。配置类错误（如模型名携带未知 provider 前缀）SHALL 返回结构化失败响应（`success=false` + `errorType` + 人话错误信息），MUST NOT 以未捕获异常 500 裸栈响应。

#### Scenario: 测试成功

- **WHEN** 用户填写了完整 LLM 配置并点击"测试连接"按钮
- **THEN** 后端 SHALL 使用该配置发送探测 LLM 请求
- **AND** 若请求成功，前端 SHALL 展示成功状态（绿色）和响应延迟（毫秒）

#### Scenario: 测试失败返回错误分类

- **WHEN** 用户点击"测试连接"但配置无效（如 API key 错误、base_url 不通、模型名不存在）
- **THEN** 前端 SHALL 展示失败状态（红色）和错误信息
- **AND** 系统 SHALL 返回错误分类（`auth` / `network` / `model_not_found` / `unknown`）便于前端展示针对性提示

#### Scenario: 认证失败时提示检查 API Key

- **WHEN** 连通性测试返回 `error_type: "auth"`
- **THEN** 前端 SHALL 展示提示 "API Key 无效，请检查密钥配置"

#### Scenario: 连接不通时提示检查 Base URL

- **WHEN** 连通性测试返回 `error_type: "network"`
- **THEN** 前端 SHALL 展示提示 "无法连接到 API 端点，请检查 Base URL"

#### Scenario: 未知 provider 前缀返回结构化错误

- **WHEN** 用户配置的模型名携带后端白名单外的 provider 前缀（如 `kimi/kimi-k2-0905-preview`）并点击"测试连接"
- **THEN** 后端 SHALL 返回结构化失败响应：`success=false`、`errorType="model_prefix_invalid"`、错误信息含已知前缀列表与「OpenAI 兼容端点请使用 openai/<model>」指引
- **AND** 响应 MUST NOT 为 HTTP 500 未捕获异常

### Requirement: 模型自动发现

系统 SHALL 提供模型自动发现功能，用户填写 base_url 后可拉取该端点支持的模型列表。模型发现请求 SHALL 由后端代理调用（非前端直连），规避 CORS 和密钥暴露问题。用户从模型列表选择模型后自动拼接的前缀 SHALL 与后端 resolver 白名单一致：域名推导出的前缀不在白名单内时 MUST 回退 `openai/`（OpenAI 兼容端点语义），不得拼出后端必然拒绝的前缀。

#### Scenario: 成功拉取模型列表

- **WHEN** 用户填写了 base_url（如 `https://api.deepseek.com/v1`）和 api_key，点击"刷新模型列表"按钮
- **THEN** 前端 SHALL 调用 `POST /api/llm-config/models` 发送 base_url 和 api_key 到后端
- **AND** 后端 SHALL 调用 `GET {base_url}/models` 拉取可用模型列表
- **AND** 前端 SHALL 将返回的模型列表渲染为下拉选择

#### Scenario: 用户从模型列表选择模型后自动拼接前缀

- **WHEN** 用户从自动发现的模型下拉中选择 `deepseek-chat`（base_url 为 `https://api.deepseek.com/v1`）
- **THEN** model 输入框 SHALL 自动填充为 `deepseek/deepseek-chat`（litellm 前缀格式）

#### Scenario: 域名推导前缀不在白名单时回退 openai

- **WHEN** 用户从自动发现的模型下拉中选择 `kimi-k2-0905-preview`（base_url 为 `https://api.kimi.ai/v1`，域名主体推导出的前缀 `kimi` 不在后端 resolver 白名单）
- **THEN** model 输入框 SHALL 自动填充为 `openai/kimi-k2-0905-preview`（回退 OpenAI 兼容前缀，避免测试连接与解析必然失败）

#### Scenario: base_url 为空时不回退环境变量（决策 A）

- **WHEN** 用户点击"刷新模型列表"但 base_url 输入框为空（如选择 OpenAI/Anthropic/自定义预设时）
- **THEN** 后端 SHALL **NOT** 回退到环境变量 `LLM_BASE_URL` 拉取模型列表
- **AND** 系统 SHALL 返回空模型列表，并提示用户"请先配置 API Base URL 再刷新模型列表"
- **AND** 分析链路 `call_llm` 的回退行为 SHALL 不受影响（仍为 请求配置 → 环境变量 → 默认值）

#### Scenario: base_url 不支持模型列表端点时优雅降级

- **WHEN** 用户点击"刷新模型列表"但 base_url 不支持 `/models` 端点（如返回 404 或非标准格式）
- **THEN** 系统 SHALL 返回空模型列表并展示提示信息（"该端点不支持模型自动发现，请手动输入"）
- **AND** 用户 SHALL 仍能手动在 model 输入框中输入模型名

#### Scenario: 模型发现请求超时或网络错误

- **WHEN** 模型发现请求超时或网络不通
- **THEN** 系统 SHALL 返回错误状态并展示错误信息（如"连接超时，请检查 Base URL"）
- **AND** 错误 SHALL 不阻塞用户继续手动配置
