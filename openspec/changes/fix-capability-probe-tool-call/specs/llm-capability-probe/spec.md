# Delta for llm-capability-probe

## MODIFIED Requirements

### Requirement: 五项能力探测

设置页「测试连接」SHALL 升级为 capability probe：对目标 profile 执行 non_stream / stream / tool_call / tool_followup / json_output 五项最小探测，返回每项结果、有效配置（profile/provider/model/base_url）与 warnings（如 `tool_choice_required_unsupported`、`provider_prefix_forced_to_openai`）。probe 结果 MUST 可修正静态能力表：冲突时以 probe 运行时事实为准并写 warning。

tool_call 探测 SHALL 采用两级判定，消除「模型不主动调用」造成的假阴性：

1. **第一级（自然调用）**：`tool_choice="auto"` + 明确指示调用探测工具的提示词；响应含结构化 `tool_calls` 即通过。
2. **第二级（强制调用兜底）**：第一级请求成功但无 `tool_calls` 时，以指定探测函数的 `tool_choice` 重试；响应含结构化 `tool_calls` 即通过，并记 warning `tool_auto_no_call_forced_ok`（观测信号，不影响判定）。

任一级的 tools 请求被端点以错误拒绝（如 4xx）时，`tool_call=false` 且 warnings MUST 含 `tool_call_probe_error`（语义：端点拒绝 tools 参数，区别于模型未调用）。

tool_followup 探测 SHALL 仅在 `tool_call=true` 时执行；`tool_call=false` 时 `tool_followup` 保持 false 且语义为「未测」（不声称不支持），前端展示契约见 llm-mode-gating。

(Previously: 设置页「测试连接」SHALL 升级为 capability probe：对目标 profile 执行 non_stream / stream / tool_call / tool_followup / json_output 五项最小探测，返回每项结果、有效配置与 warnings。probe 结果 MUST 可修正静态能力表：冲突时以 probe 运行时事实为准并写 warning。tool_call 探测为单级 `tool_choice="auto"` 弱提示判定，未区分「端点拒绝」与「模型未调用」；tool_followup 仅在 tool_call 通过后执行但结果语义未定义「未测」态。)

#### Scenario: 假可用被识别

- **WHEN** 某 profile 能完成 non_stream 聊天但 tool_call 两级探测均被端点拒绝（如参数被静默 drop 或端点 400）
- **THEN** 测试结果返回 `tool_call=false` 且 warnings 含 `tool_call_probe_error`，前端能力矩阵明示「能聊天但不能跑 Agent」并提示检查端点套餐/权限

#### Scenario: 模型不主动调用不再是假阴性

- **GIVEN** 端点支持 tools 参数，但模型对第一级提示未主动调用探测工具
- **WHEN** 第二级强制 `tool_choice` 请求返回结构化 `tool_calls`
- **THEN** `tool_call=true`，warnings 含 `tool_auto_no_call_forced_ok`（不影响判定）

#### Scenario: 工具跟随未测态

- **WHEN** `tool_call=false`
- **THEN** `tool_followup` 不执行、保持 false，语义为「未测」而非「不支持」

#### Scenario: 前端按能力禁用入口

- **WHEN** 生效 profile 的 `tool_call=false`
- **THEN** 前端禁用深度 ReAct 入口并提示切换 profile 或走 fast path，不等待运行中失败
