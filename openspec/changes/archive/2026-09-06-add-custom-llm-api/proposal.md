## Why

当前系统 LLM 配置完全依赖后端环境变量（`LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_THINKING` 等），用户无法在运行时切换模型、更改 API 端点或调整参数。前端唯一的配置入口是 API Key 输入弹窗，不暴露 model、base_url、思考模式等设置。对于需要使用不同 LLM 提供商（如 OpenAI、Anthropic、本地 Ollama）或不同模型变体的用户，当前架构缺乏灵活性。

## What Changes

- 新增前端**设置面板**（Settings Panel），取代现有仅输入 API Key 的弹窗，支持配置：
  - **API Key**（已有，保留）
  - **模型名称**（litellm 格式，如 `deepseek/deepseek-chat`、`openai/gpt-4o`）
  - **API Base URL**（OpenAI 兼容端点，如 `https://api.deepseek.com/v1`）
  - **思考模式**（enabled / disabled，仅 DeepSeek 系列生效）
- 前端配置持久化到 `localStorage`，刷新不丢失
- 后端 API（`/api/chat`、`/api/analyze`）接受请求体中的 LLM 配置字段，覆盖环境变量默认值
- 后端 LLM 调用链路（管线节点 `llm.py` + ReAct harness `litellm_client.py`）支持按请求级别的 LLM 配置注入
- 新增后端 `/api/llm-config` 端点，返回当前生效的默认配置（model、base_url、thinking），供前端展示占位符和默认值
- 新增**Provider 预设**（借鉴 [cc-switch](https://github.com/farion1231/cc-switch)）：设置面板内置常用 LLM 提供商快捷预设（DeepSeek 官方、OpenAI、Anthropic、本地 Ollama、自定义），用户选择预设后自动填充 model 前缀和 base_url，降低手动输入出错率
- 新增**模型自动发现**（借鉴 cc-switch v3.13）：用户填好 base_url + api_key 后，可点击"刷新模型列表"按钮，后端调用 OpenAI 兼容的 `GET {base_url}/models` 端点拉取可用模型，前端展示为下拉选择
- 新增**连通性测试**（借鉴 cc-switch）：设置面板提供"测试连接"按钮，后端用当前配置发送一个极简 LLM 请求验证配置有效性，返回成功/失败 + 错误信息，避免用户保存错误配置后分析中途失败
- 新增**多配置管理**：设置面板支持将当前配置「另存为」命名 profile（如「DeepSeek 办公」「OpenAI 测试」「本地 Ollama」），可删除；多套配置持久化到 localStorage，同一时刻一个 profile 生效
- 新增**LLM 切换下拉框**：在模式选择器（快速模式/深度研究）右侧新增 LLM 切换下拉框，列出全部已保存 profile，选中即切换生效，无需打开设置面板；EmptyState 与聊天输入区两处均可见

## Capabilities

### New Capabilities

- `llm-config`: 用户自定义 LLM 配置能力——前端设置面板收集 model / base_url / api_key / thinking，后端按请求注入 LLM 客户端，覆盖环境变量默认值

### Modified Capabilities

（无现有 spec 需要修改——当前 `session-streaming`、`pipeline-events`、`frontend` 等规格不涉及 LLM 配置行为）

## Impact

- **后端代码**：
  - [llm.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/llm.py) — `call_llm` / `call_llm_stream` / `call_llm_with_tools` 接受请求级 LLM 配置
  - [agent_factory.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py) — `build_agent` / `_make_llm_client` 支持动态配置注入
  - [harness/litellm_client.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py) — `LiteLLMClient` 支持动态 base_url / model
  - [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) — 请求体新增 LLM 配置字段 + `/api/llm-config` 端点
- **前端代码**：
  - [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) — 扩展 `ApiKeyModal` 为完整设置面板，请求提交携带 LLM 配置；新增 LLM 切换下拉框（EmptyState + ChatInputBar）
  - [llmConfig.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/llmConfig.ts) — 新增多 profile 数据结构（`fa_llm_profiles`）与增删改查/切换激活/旧配置迁移逻辑
- **API 契约**：`/api/chat`、`/api/analyze` 请求体新增可选字段 `llm_config`
- **依赖**：无新增依赖（后端复用 LiteLLM 现有能力，前端复用原生 fetch + localStorage）
