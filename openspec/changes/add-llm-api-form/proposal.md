# Proposal: add-llm-api-form

## Why

当前 LLM 设置面板只配置 model / base_url / api_key / thinking，模型名称必须手写成带 provider 前缀的 litellm 格式（如 `openai/gpt-4o`、`anthropic/claude-sonnet-4-20250514`），面板上看不出该配置走的是 Chat Completion、Anthropic Messages 还是新的 Responses 协议。用户无法显式指定协议，模型名前缀也强制手工维护。

## What Changes

- 设置面板新增 **API 形式（API Form）** 下拉框，可选项（带 OpenAI / Anthropic 字样）：
  - **OpenAI Chat Completion**（`/chat/completions`）
  - **Anthropic Messages**（`/v1/messages`）
  - **OpenAI Responses**（`/responses`）
- 模型名称输入框 **允许填裸模型名**（如 `gpt-4o`、`claude-sonnet-4-20250514`），provider 前缀由所选「API 形式」推导并内部补全；已含 `/` 前缀的模型名（如 `deepseek/deepseek-chat`）原样使用
- 选择值持久化进 profile 配置（`apiForm` 字段），随请求级 `llm_config.apiForm` 下发
- 后端将 `apiForm` 映射为 litellm 调用的 `api` 参数（`chat` / `messages` / `responses`），驱动端点协议
- **缺省默认 OpenAI Chat Completion**：未显式选择时落定为 `chat_completion`（无「跟随默认」空态）；不经前端的直连客户端不传 `apiForm` 时仍由 litellm 按 model 前缀自动路由（向后兼容）

## Capabilities

### New Capabilities

（无新增 capability——归属既有 `llm-config` 能力）

### Modified Capabilities

- `llm-config`: 新增 API 形式选择（显式指定 OpenAI/Anthropic 协议）与模型名前缀推导，随请求级配置下发到后端 litellm 调用

## Impact

- **后端代码**：
  - [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) — `LLMConfigRequest` 新增可选 `apiForm` 字段（三值枚举 + 校验器拒绝非法值）；`_to_llm_config` 透传
  - [llm/legacy.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/llm/legacy.py) — `LLMConfig` 新增 `apiForm`；`_request_config_dict` 透传
  - [llm/gateway.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/llm/gateway.py)（及 `litellm_adapter.py`）— 将 profile 上的 `apiForm` 映射为 litellm 请求 kwargs 的 `api` 参数
  - 请求级配置 → profile 的解析链路上透传 `apiForm`
- **前端代码**：
  - [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) — `SettingsModal` 新增「API 形式」下拉框，随保存写入 config
  - [llmConfig.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/llmConfig.ts) — `LLMConfig` 新增 `apiForm` 字段；新增裸模型名前缀推导逻辑；`buildLlmConfigPayload` 透传；Provider 预设可携带对应 `apiForm`
- **API 契约**：`/api/chat`、`/api/analyze` 请求体 `llm_config` 新增可选字段 `apiForm`
- **依赖**：无新增（复用 litellm 既有 `api` 参数）
