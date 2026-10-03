# Delta for llm-mode-gating

## MODIFIED Requirements

### Requirement: 前端能力矩阵展示

设置页 SHALL 展示当前 profile 的能力矩阵（non_stream/stream/tool_call/tool_followup/json_output），数据来自 `/api/llm-config/test` 返回的 probe 结果；probe 未完成时显示「未探测」提示（前端无静态 capability 来源，静态声明仅存在于后端 resolver），完成后以 probe 事实更新。

矩阵 SHALL 区分三种呈现态：**通过**（绿色 ✓）、**不支持**（红色 ✗，实测失败）、**未测**（中性态，因前置项未通过而未执行）。`tool_followup` 在 `tool_call=false` 时 SHALL 呈现「未测」，MUST NOT 显示「不支持」；仅 `tool_call=true` 且 `tool_followup=false` 时显示「不支持」。

probe warnings SHALL 经机器码 → 人话映射后展示，映射 MUST 覆盖：`tool_call_probe_error`（工具调用请求被端点拒绝，提示检查该 API 套餐/权限是否支持 tools）、`tool_auto_no_call_forced_ok`（模型未主动调用工具，强制调用通过）、`json_mode_unsupported`、`stream_unsupported`；未知码原样展示。

#### Scenario: probe 结果驱动矩阵

- **WHEN** 设置页完成一次连通性测试
- **THEN** 能力矩阵按 probe 事实渲染（逐项通过/失败态可区分）

#### Scenario: 工具跟随级联未测态

- **GIVEN** probe 事实 `tool_call=false`、`tool_followup=false`
- **WHEN** 渲染能力矩阵
- **THEN** 「工具调用」呈不支持态（红色 ✗），「工具跟随」呈「未测」中性态，不显示「不支持」

#### Scenario: warnings 人话化

- **GIVEN** probe 返回 warnings 含 `tool_call_probe_error`
- **WHEN** 渲染能力矩阵 warnings 列表
- **THEN** 展示映射后的中文可行动提示（含检查套餐/权限指引），而非裸机器码；未知码原样展示
