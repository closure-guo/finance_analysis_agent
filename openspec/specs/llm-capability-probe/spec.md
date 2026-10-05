# llm-capability-probe Specification

## Purpose

定义 LLM provider 能力探测（capability probe）契约：设置页「测试连接」升级为五项能力探测（non_stream/stream/tool_call/tool_followup/json_output），probe 结果缓存与事实回写解析链，Provider 合同测试门禁，以及关键参数不静默丢弃。probe 运行时事实 SHALL 优先于 registry 静态能力表，冲突时以 probe 为准并写 warning。

## Requirements

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

### Requirement: Provider 合同测试门禁

每个启用的 profile MUST 通过同一组合同测试（`tests/llm_contracts/`：文本/流式/单工具调用/工具结果回传/JSON 输出合同/截断分类/鉴权错误分类/限流可重试/未知前缀拒绝/深度与快速不串 provider）。门禁规则：未通过 `tool_call_single + tool_result_followup` 的 profile MUST NOT 用于生产深度模式；未通过 `json_output_contract` 的 profile MUST NOT 用于管线节点。litellm 升级、模型 alias 变更、prompt 变更 MUST 触发合同测试。

#### Scenario: 弱工具 profile 禁入深度模式

- **WHEN** 某新 provider profile 的合同测试中 tool_result_followup 失败
- **THEN** 该 profile 不出现在生产深度模式下拉选项中（或标红禁用），直到合同通过

#### Scenario: 依赖升级触发合同

- **WHEN** litellm 版本或模型 alias 变更的 PR 提交
- **THEN** CI 自动执行全部启用 profile 的合同测试，失败阻断合并

### Requirement: 关键参数不静默丢弃

`tools/tool_choice/response_format/max_tokens/stream` 等关键参数 MUST NOT 被全局 `drop_params` 静默吞掉；provider 不支持时 adapter SHALL 显式报 `UnsupportedCapabilityError` 或走声明的 fallback（如不支持 tools 的 provider 降级 action 文本协议），并在 trace 记录 degradation。

#### Scenario: 弱工具 provider 显式降级

- **WHEN** profile 的 `capability.tools == none` 且业务请求带 tools
- **THEN** ReAct 走 action 文本协议兜底（`<action name="...">{json}</action>` + `<observation>` 回填），trace 记录 degradation=action_protocol，不伪造 provider tool message

### Requirement: probe 结果缓存与失效

probe 结果 SHALL 被缓存；缓存键 MUST 至少包含 provider、model、base_url、api_key hash、litellm version。baseUrl、model、key、litellm 版本任一变化后缓存 MUST 失效并重新探测。

#### Scenario: 同配置重复探测命中缓存

- **WHEN** 同一 provider/model/base_url/api_key/litellm 版本组合在缓存有效期内再次触发 probe
- **THEN** 直接返回缓存的 ProbeResult，不发起真实 LLM 请求

#### Scenario: 配置变更后缓存失效

- **WHEN** 同组合中 model 或 api_key 发生变化后再次触发 probe
- **THEN** 缓存未命中，重新执行探测并用新结果覆盖缓存

### Requirement: probe 事实回写解析链

resolver 解析 profile 时 SHALL 尝试合并 probe 缓存事实与 registry 静态 capability：冲突字段以 probe 结果为准并在 trace 记 warning；缓存不可用时使用静态 capability 并在 profile 标记 `probe_required`。probe SHALL NOT 修改 provider_options 与密钥。

#### Scenario: 静态声称支持工具但 probe 失败

- **WHEN** registry 静态 capability 声明 tools!=none 而 probe 事实 tool_call=false
- **THEN** 解析出的 profile capability.tools 为 none（probe 优先），trace 记录 warning

#### Scenario: 无缓存时标记待探测

- **WHEN** 该组合无有效 probe 缓存
- **THEN** profile 使用静态 capability 且带 probe_required 标记，不阻塞调用
