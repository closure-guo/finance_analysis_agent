# Proposal: add-context-length-config

## Why
模型真实上下文窗口差异大（方舟 GLM 远大于 registry 静态声明的 128000），用户无法按所用端点调整；ReAct 历史压缩时机因此偏早或偏晚。G-Task 5 已把 ContextBudget 改为按 `capability.max_context` 派生，但该值目前只有 registry 静态表一个来源，缺请求级配置入口。

## What Changes
- 前端设置页新增「上下文长度（tokens）」输入（留空跟随默认），随 `llm_config.contextLength` 下发。
- 后端 `LLMConfigRequest`/`LLMConfig` 增加 `contextLength` 字段并全链透传；resolver 请求级分支用其覆盖 `capability.max_context`；环境变量 `LLM_MAX_CONTEXT` 提供无请求配置时的调参口。
- harness `ContextBudget` 经 G-Task 5 既有接线自动生效（无新改动）。

## Capabilities
- **Modified Capabilities**: `llm-provider-gateway`（ProfileResolver 支持请求级 contextLength 覆盖 max_context）

## Impact
前端 App.tsx/llmConfig.ts；后端 api.py/_to_llm_config、legacy `_request_config_dict`、resolver.py；不改 ContextBudget/agent_factory（已支持）。
