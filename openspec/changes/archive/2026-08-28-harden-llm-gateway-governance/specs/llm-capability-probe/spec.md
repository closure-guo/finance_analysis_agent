## MODIFIED Requirements

### Requirement: probe 结果缓存与失效

probe 结果 SHALL 被缓存；缓存键 MUST 至少包含 provider、model、base_url、api_key hash、litellm version。baseUrl、model、key、litellm 版本任一变化后缓存 MUST 失效并重新探测。
(Previously: probes.py 每次调用全量执行五项探测，无缓存。)

#### Scenario: 同配置重复探测命中缓存
- **WHEN** 同一 provider/model/base_url/api_key/litellm 版本组合在缓存有效期内再次触发 probe
- **THEN** 直接返回缓存的 ProbeResult，不发起真实 LLM 请求

#### Scenario: 配置变更后缓存失效
- **WHEN** 同组合中 model 或 api_key 发生变化后再次触发 probe
- **THEN** 缓存未命中，重新执行探测并用新结果覆盖缓存

### Requirement: probe 事实回写解析链

resolver 解析 profile 时 SHALL 尝试合并 probe 缓存事实与 registry 静态 capability：冲突字段以 probe 结果为准并在 trace 记 warning；缓存不可用时使用静态 capability 并在 profile 标记 `probe_required`。probe SHALL NOT 修改 provider_options 与密钥。
(Previously: resolver 只使用 registry 静态 capability，probe 结果与 profile 解析互不相交。)

#### Scenario: 静态声称支持工具但 probe 失败
- **WHEN** registry 静态 capability 声明 tools!=none 而 probe 事实 tool_call=false
- **THEN** 解析出的 profile capability.tools 为 none（probe 优先），trace 记录 warning

#### Scenario: 无缓存时标记待探测
- **WHEN** 该组合无有效 probe 缓存
- **THEN** profile 使用静态 capability 且带 probe_required 标记，不阻塞调用
