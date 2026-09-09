# Delta for llm-config

## MODIFIED Requirements

### Requirement: 前端设置面板支持自定义 LLM 配置

系统 SHALL 在前端提供设置面板（LLM 配置），允许用户配置 model（模型名称）、base_url（API 端点）、api_key（API 密钥）、thinking（思考模式开关）等 LLM 参数，配置持久化到浏览器 localStorage。设置面板 SHALL 位于设置中心页 `/settings` 的「LLM 配置」分区内（由 SettingsModal 弹窗整体迁移而来），通过左侧垂直导航访问；配置字段、Provider 预设、模型自动发现、连通性测试与多 profile 管理行为语义不变。

#### Scenario: 设置面板展示配置字段

- **GIVEN** 用户进入设置中心页「LLM 配置」分区
- **THEN** 面板 SHALL 展示配置项：API Key（密码输入框）、模型名称（文本输入框）、API Base URL（文本输入框）、思考模式（Toggle 开关，enabled/disabled）等

#### Scenario: 配置持久化到 localStorage

- **WHEN** 用户在设置面板修改任意配置项并保存
- **THEN** 系统 SHALL 将配置序列化为 JSON 存入浏览器 localStorage（`fa_llm_profiles` / 激活 profile）
- **AND** 页面刷新后重新进入「LLM 配置」分区时，SHALL 恢复上次保存的配置

#### Scenario: 设置面板占位符显示后端默认值

- **WHEN** 设置面板首次加载（无已保存配置）
- **THEN** 模型名称输入框的 placeholder SHALL 显示后端默认模型（从 `GET /api/llm-config` 获取）
- **AND** API Base URL 输入框的 placeholder SHALL 显示后端默认 base_url
- **AND** 思考模式开关 SHALL 默认设为后端默认值

#### Scenario: 设置面板向后兼容现有 API Key

- **WHEN** localStorage 中存在旧 key `fa_api_key` 且无已保存 profile
- **THEN** 系统 SHALL 自动迁移：将 `fa_api_key` 的值读入首个 profile 的 api_key，并清除旧 key

#### Scenario: 无 profile 强制配置跳转设置页

- **WHEN** 用户尝试发起分析/聊天但无任何 LLM profile
- **THEN** 系统 SHALL 阻止发送并跳转 `/settings` 设置中心页，定位到「LLM 配置」分区
- **AND** 用户保存配置创建首个 profile 后方可发起分析

## ADDED Requirements

### Requirement: LLM 切换下拉框提供「LLM 配置…」分隔项

系统 SHALL 在 LLM 切换下拉框（profile 列表）底部以分隔线隔开一个「LLM 配置…」项，点击后跳转 `/settings` 设置中心页并定位「LLM 配置」分区；该分隔项 SHALL NOT 改变当前激活 profile。

#### Scenario: 下拉框显示分隔项

- **GIVEN** 用户展开 LLM 切换下拉框且存在若干 profile
- **THEN** 下拉框 SHALL 在 profile 列表底部以分隔线展示「LLM 配置…」项

#### Scenario: 点击分隔项跳转设置页

- **WHEN** 用户点击「LLM 配置…」项
- **THEN** 系统 SHALL 跳转到 `/settings` 设置中心页并定位「LLM 配置」分区

#### Scenario: 分隔项不改变激活 profile

- **GIVEN** 用户展开 LLM 切换下拉框时已激活 profile P
- **WHEN** 用户点击「LLM 配置…」分隔项
- **THEN** 激活 profile 仍为 P
- **AND** 后续请求 SHALL 仍携带 profile P 的配置
