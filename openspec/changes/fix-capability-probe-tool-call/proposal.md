# Proposal: fix-capability-probe-tool-call

## Why

用户把股票分析 agent 切换到 Kimi（OpenAI 兼容端点，官方支持 tools）后，能力探测把「工具调用」判为不支持：探针用 `tool_choice="auto"` + 弱提示「说你好」，模型不主动调工具即记 false——假阴性。误判事实写入 probe 缓存（24h）后 `capability.tools=none`，深度分析被网关硬拦（后端日志实锤：`UnsupportedCapabilityError`，两次 `/api/analyze` 失败）。配套还有三道墙：`tool_followup` 级联显示「不支持」实为「未测」；warnings 只有机器码（`tool_call_probe_error` 用户看不懂）；`/api/llm-config/test` 对未知前缀（`kimi/…`）直接 500 裸栈，且前端模型发现的域名前缀推导（api.kimi.ai → `kimi/`）与 resolver 白名单不一致，是新 provider 接入的第一道坎。

## What Changes

- **tool_call 探测改两级判定**：第一级 `tool_choice="auto"` + 明确工具调用指令的提示词；未调用但请求成功时，第二级以指定函数的 `tool_choice` 强制调用兜底。任一级返回结构化 `tool_calls` 即 `tool_call=true`（仅强制级通过时记 warning `tool_auto_no_call_forced_ok`）
- **warnings 语义化**：端点拒绝 tools 请求（HTTP 错误）→ `tool_call_probe_error`（「端点不支持」）；模型未调用但强制级通过 → `tool_auto_no_call_forced_ok`（观测信号，不影响判定）。两者可区分
- **tool_followup 未测态**：`tool_call=false` 时 `tool_followup` 不再执行；前端矩阵该项显示「未测」（中性态）而非「不支持」（失败态）；仅 `tool_call=true && tool_followup=false` 显示「不支持」
- **warnings 人话化**：前端将机器码映射为中文可行动提示（如 `tool_call_probe_error` → 提示检查套餐/权限是否支持 tools），未知码原样展示
- **`/api/llm-config/test` 结构化错误**：未知 provider 前缀等配置错误返回 `success=false` + `errorType=model_prefix_invalid` + 人话错误信息，不再 500 裸栈
- **前端前缀推导白名单回退**：`buildModelWithPrefix` 域名推导出的前缀不在 resolver 白名单（openai/deepseek/anthropic/gemini）时回退 `openai/`，与后端 `_ensure_prefix` 语义对齐

## Capabilities

- **New Capabilities**: 无
- **Modified Capabilities**:
  - `llm-capability-probe`：五项探测中 tool_call 的判定口径（auto 单级 → 两级）、warnings 语义、tool_followup 级联语义
  - `llm-config`：连通性测试对配置类错误的结构化返回；模型自动发现的前缀推导白名单回退
  - `llm-mode-gating`：能力矩阵的「未测」态展示与 warnings 人话化

## Impact

- 后端：`src/finance_agent/llm/probes.py`（两级判定）、`src/finance_agent/api.py`（test 端点错误处理）
- 前端：`frontend/src/llmConfig.ts`（前缀回退）、`frontend/src/pages/settings/panes/LlmConfigPane.tsx`（未测态 + warnings 映射）
- 测试：`tests/llm/test_probes.py`、`tests/test_api_llm_config.py`、`frontend/src/test/llmConfig.test.ts`、`frontend/src/test/capabilityGating.test.ts`
- 不改变 probe 缓存机制、`judge_capability_from_probe` 的 tools=json 判定、模式门禁规则本身
