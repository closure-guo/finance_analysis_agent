# Delta for llm-config

## ADDED Requirements

### Requirement: API 形式配置

设置面板 SHALL 提供「API 形式」下拉框，可选项为 OpenAI Chat Completion、Anthropic Messages、OpenAI Responses；所选值 SHALL 持久化到 profile 配置（`apiForm` 字段）并随请求级 `llm_config.apiForm` 下发，后端 SHALL 据此映射 litellm 调用的 `api` 参数。未显式配置时 SHALL 默认 OpenAI Chat Completion（`chat_completion`）。

#### Scenario: 设置面板展示 API 形式下拉框
- **WHEN** 用户打开设置面板
- **THEN** 面板 SHALL 展示「API 形式」下拉框
- **AND** 可选项 SHALL 包含 `chat_completion`（OpenAI Chat Completion）、`messages`（Anthropic Messages）、`responses`（OpenAI Responses）三者
- **AND** 未选择过时 SHALL 默认选中 OpenAI Chat Completion（无「跟随默认」空态）

#### Scenario: 选择 OpenAI Chat Completion
- **WHEN** 用户在「API 形式」下拉框选择 `chat_completion` 并保存
- **THEN** profile 配置 SHALL 持久化 `apiForm = "chat_completion"`
- **AND** 后端 litellm 调用 SHALL 使用 `api = "chat"`（`/chat/completions` 协议）

#### Scenario: 选择 Anthropic Messages
- **WHEN** 用户在「API 形式」下拉框选择 `messages` 并保存
- **THEN** profile 配置 SHALL 持久化 `apiForm = "messages"`
- **AND** 后端 litellm 调用 SHALL 使用 `api = "messages"`（`/v1/messages` 协议）

#### Scenario: 选择 OpenAI Responses
- **WHEN** 用户在「API 形式」下拉框选择 `responses` 并保存
- **THEN** profile 配置 SHALL 持久化 `apiForm = "responses"`
- **AND** 后端 litellm 调用 SHALL 使用 `api = "responses"`（Responses 协议）

#### Scenario: 缺省默认 OpenAI Chat Completion
- **WHEN** 配置未显式设置 `apiForm`（前端缺省值落定为 `chat_completion`）
- **THEN** 请求级 `llm_config.apiForm` SHALL 为 `"chat_completion"`
- **AND** 后端 litellm 调用 SHALL 使用 `api = "chat"`

#### Scenario: 请求携带 API 形式
- **WHEN** 请求级 `llm_config.apiForm` 已设置
- **THEN** 请求体 `llm_config.apiForm` SHALL 等于该 profile 保存的值

#### Scenario: 直接 API 客户端缺省 apiForm（兼容）
- **WHEN** 直连客户端（不经前端）请求级 `llm_config.apiForm` 为 null 或缺失
- **THEN** 系统 SHALL 不显式设置 litellm `api` 参数
- **AND** 协议选择 SHALL 交由 litellm 按 model 前缀自动路由（仅供无前端直连场景的向后兼容）

#### Scenario: API 形式随 profile 切换
- **WHEN** 用户从 LLM 切换下拉框切换到一个携带不同 `apiForm` 的 profile
- **THEN** 后续请求 SHALL 使用该 profile 的 `apiForm` 值
- **AND** 设置面板「API 形式」下拉框 SHALL 显示该 profile 已保存的 `apiForm`

#### Scenario: 非法 API 形式值拒绝
- **WHEN** 请求级 `llm_config.apiForm` 既非 `chat_completion` 亦非 `messages` 亦非 `responses`
- **THEN** 系统 SHALL 返回配置错误（HTTP 422），不得静默忽略或误映射

### Requirement: 模型名称前缀推导

模型名称输入框 SHALL 允许用户填写不带 provider 前缀的裸模型名（如 `gpt-4o`、`claude-sonnet-4-20250514`）；系统调度 LLM 时 SHALL 依据所选「API 形式」推导并内部补全 litellm 前缀。若模型名已含 `/` 前缀（如 `deepseek/deepseek-chat`），系统 SHALL 原样使用，不做推导。

#### Scenario: 裸模型名按 API 形式补全前缀
- **WHEN** 用户在设置面板选择 API 形式 `chat_completion` 并填写裸模型名 `gpt-4o`
- **THEN** 生效的模型 SHALL 为 `openai/gpt-4o`（补全 `openai` 前缀）
- **WHEN** 用户在设置面板选择 API 形式 `messages` 并填写裸模型名 `claude-sonnet-4-20250514`
- **THEN** 生效的模型 SHALL 为 `anthropic/claude-sonnet-4-20250514`（补全 `anthropic` 前缀）
- **WHEN** 用户在设置面板选择 API 形式 `responses` 并填写裸模型名 `gpt-4o-mini`
- **THEN** 生效的模型 SHALL 为 `openai/gpt-4o-mini`（补全 `openai` 前缀）

#### Scenario: 已含前缀的模型名原样使用
- **WHEN** 用户在设置面板填写模型名 `deepseek/deepseek-chat`（已含 `/` 前缀）
- **THEN** 生效的模型 SHALL 保持 `deepseek/deepseek-chat`，不做任何前缀推导

#### Scenario: 未设置 API 形式时不推导
- **WHEN** 用户未设置「API 形式」下拉框（apiForm 为空）
- **THEN** 系统 SHALL 不对模型名做前缀推导，原样下发
- **AND** 行为与引入本功能前完全一致
