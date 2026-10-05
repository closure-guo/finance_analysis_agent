# Design: fix-capability-probe-tool-call

## Approach

**两级 tool_call 探测（probes.py `run_live_probes`）**。第一级保持 `tool_choice="auto"` 但把提示词从「说你好」改为明确指示调用 `probe_echo` 的指令（测「模型 + 端点」的自然工具使用）；请求成功而无 `tool_calls` 时，第二级用 `tool_choice={"type":"function","function":{"name":"probe_echo"}}` 强制调用（测「端点是否支持 tools」）。任一级拿到结构化 `tool_calls` 即 `tool_call=true`，tool_followup 复用命中那一级的 `tool_calls` 构造回传。两级都请求错误 → `tool_call=false` + warning `tool_call_probe_error`；仅第二级命中 → 追加 warning `tool_auto_no_call_forced_ok`。判定层（`judge_capability_from_probe`/`merge_probe_into_profile`）零改动——仍是布尔事实。

**test 端点结构化错误（api.py）**。`_ensure_prefix` 调用挪进 try，捕获 `UnknownProviderPrefixError` 返回 `success=false, errorType="model_prefix_invalid"` + 原异常文案（本身已是人话：已知前缀列表 + openai/ 指引）。

**前端（llmConfig.ts / LlmConfigPane.tsx）**。`buildModelWithPrefix` 推导前缀后对白名单 `['openai','deepseek','anthropic','gemini']`（与 resolver `_KNOWN_PREFIXES` 对齐）做过滤，不在白名单回退 `openai/`。矩阵渲染新增第三态：`tool_followup===false && tool_call===false` → 「未测」（中性色，无 ✗ 图标）；warnings 经 `PROBE_WARNING_LABELS` 映射表转人话，未知码透传。

## Alternatives Considered

- **只保留强制 tool_choice 单级**：实现最小，但对「支持 tools、不支持指定函数 tool_choice」的端点（部分网关只认 auto/none）会产生新的假阴性——两级兜底覆盖两端。
- **warnings 在后端本地化**：probe 缓存里存的是机器码（跨端契约），本地化放展示层即可，不动缓存结构与后端契约。
- **tool_followup 引入三值（untested）改后端响应结构**：布尔 + 前端级联推导等价，避免破坏 `/api/llm-config/test` 响应契约与 `parseCapability` 兼容。

## Risks

- 强制 tool_choice 请求个别端点返回 200 但忽略强制（回纯文本）→ 第二级无 `tool_calls` 判 false，与现状同，不劣化。
- 每次探测多至多一次真实 LLM 调用（仅第一级未命中时），探测频率低（手动触发）+ 24h 缓存，成本可忽略。
- 前端白名单与 resolver 白名单双份维护 → 以注释互相锚定， resolver 变更时合同测试（未知前缀拒绝）与前端单测（回退行为）双重护栏。
