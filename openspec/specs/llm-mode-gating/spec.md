# llm-mode-gating Specification

## Purpose

定义前端模式入口按 provider 能力门禁的契约：设置页能力矩阵展示 probe 事实（non_stream/stream/tool_call/tool_followup/json_output），深度 ReAct 与管线结构化入口按 capability 禁用/降级并显示原因。门禁 SHALL 消费 probe 事实，probe 优先于静态声明。

## Requirements

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

### Requirement: 模式入口按 capability 门禁

前端 SHALL 按 capability 禁用不满足要求的模式入口并显示原因：`tool_call=false` 的 profile 禁用深度 ReAct（提示可切换 profile 或使用快速模式）；管线结构化入口在 `json_output=false` 时显示降级提示（JSON 输出不可用，结构化节点质量可能下降），不禁用入口。门禁 SHALL 消费 probe 事实（probe 优先于静态声明）。被禁用入口 MUST 显示禁用原因，不得静默隐藏。

#### Scenario: 无工具能力禁用深度模式

- **GIVEN** 当前 profile probe 事实 tool_call=false
- **WHEN** 用户尝试进入深度 ReAct 模式
- **THEN** 入口呈禁用态并显示「该 provider 不支持工具调用」及可行动建议

#### Scenario: probe 修正静态声明

- **GIVEN** 静态 capability 声明 tools!=none 但 probe 事实 tool_call=false
- **WHEN** 渲染模式入口
- **THEN** 门禁按 probe 事实（false）判定，而非静态声明
