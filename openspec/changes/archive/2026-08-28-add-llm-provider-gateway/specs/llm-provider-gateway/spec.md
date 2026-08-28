## ADDED Requirements

### Requirement: Provider 能力契约显式化

系统 SHALL NOT 以模型名字符串猜测 provider 能力（如 `_is_deepseek(model)` 分支）；所有 LLM 调用路径 SHALL 依据 `Capability` 契约字段决策，`Capability` 至少包含：`tools`（none/single/parallel）、`streaming`、`streaming_tool_calls`、`json_schema`（none/json_mode/strict_schema）、`reasoning_field`（下发字段名，不支持为 None）、`reasoning_must_echo_on_tool`（工具轮次是否必须回传思考字段）、`reasoning_forced`（思考是否强制开启不可关）、`max_context`、`max_output`。

#### Scenario: 方舟 GLM reasoning 字段不回传
- **WHEN** provider 的 `reasoning_must_echo_on_tool` 为 false（如方舟 GLM）且 ReAct 多轮工具调用构造回传消息
- **THEN** assistant 消息不得携带 `reasoning_content` 字段，请求被端点接受

#### Scenario: DeepSeek reasoning 字段必须回传
- **WHEN** provider 的 `reasoning_must_echo_on_tool` 为 true（如 DeepSeek 官方）且工具调用轮次回传
- **THEN** assistant 消息携带 `reasoning_content` 字段，缺失时由合同测试标记失败

#### Scenario: 强制 thinking 影响输出预算
- **WHEN** provider 的 `reasoning_forced` 为 true（如方舟 GLM，`thinking.type=disabled` 被端点 400 拒绝）
- **THEN** resolver 按 `reasoning_forced` 派生 max_tokens 预算策略（reasoning 与正文共享配额时预算必须覆盖 reasoning 峰值），并在 trace 中标记 `reasoning_forced=true`

### Requirement: 唯一配置解析入口（ProfileResolver）

model/baseUrl/apiKey/thinking/quick/deep 的优先级解析 SHALL 仅存在于 `ProfileResolver` 一处：请求级 `llm_config` → 激活 profile → 环境变量 → registry 默认。请求级配置存在时 MUST 组成完整 profile，缺关键字段显式报错或整体回退命名 profile，禁止半套配置漂移（如 judge 回退 LLM_* 打错网关）。

#### Scenario: 半套请求配置被拒绝
- **WHEN** 请求级 llm_config 只提供 model 不提供 base_url/api_key 且无对应命名 profile
- **THEN** 解析器返回显式配置错误，不得将请求 model 与环境变量 key/base_url 混搭

#### Scenario: 自定义端点模型前缀
- **WHEN** 配置了自定义 `base_url` 且 model 无 provider 前缀
- **THEN** 统一路由为 `openai/<model>`；model 已含前缀但 registry 未识别该 provider 时显式报错并提示可用前缀

#### Scenario: 同会话不串 provider
- **WHEN** 同一用户会话内发生 deep、quick、follow-up、tool follow-up 调用
- **THEN** trace 中这些调用的 provider/model 一致（除非显式 fallback 被记录），purpose 只决定档位不决定 provider

### Requirement: litellm 适配收口

`src/finance_agent/` 内除 `llm/adapters/**` 与兼容薄壳外 SHALL NOT import litellm（CI grep 门禁）。消息序列化、reasoning 字段读写、tool delta 合并、`finish_reason` 归一化（stop/tool_calls/length/content_filter/error/unknown）、错误归一化（AuthError/RateLimitError/TimeoutError/ModelNotFound/ContextOverflow/ContentFiltered/UnsupportedCapability/UnknownLLMError）SHALL 仅存在于 adapter。

#### Scenario: grep 门禁
- **WHEN** CI 执行 `grep -R "import litellm" src/finance_agent`
- **THEN** 命中范围仅限 `llm/adapters/**` 与声明了 deprecation 的兼容薄壳，否则构建失败

#### Scenario: 模型下发 arguments 不合法时回传规范化
- **WHEN** 模型输出的 `tool_calls[].function.arguments` 为非合法 JSON 字符串（如单引号 Python 字面量）且需要回传
- **THEN** adapter 在回传前将其规范化为合法 JSON（可解析则重序列化，不可解析保留原值并记 trace warning），请求被严格端点接受

#### Scenario: finish_reason 分类处理
- **WHEN** 流式结束 `finish_reason` 为 length / content_filter / None 且无正文 delta
- **THEN** 分别归类为 OutputTruncated（触发 max_tokens 复核或 repair）/ ContentFiltered（不盲目重试）/ EmptyLLMOutput（触发重试路径），不再表现为下游偶发 JSONDecodeError

### Requirement: litellm 运行时防护

litellm 运行时开关（流式 logging 禁用、请求级 timeout）与库级平台 bug 防护 SHALL 统一在 adapter 初始化处设置，业务模块 MUST NOT 各自设置。adapter 测试套件 SHALL 包含线程/端口泄漏守护（incident 016 回归：流式调用后线程数与本地监听端口数不增长）。

#### Scenario: 死锁开关统一收口
- **WHEN** 任意入口（管线 llm 薄壳、harness、evals）首次触发 adapter 初始化
- **THEN** `litellm.disable_streaming_logging` 等运行时开关已生效，业务模块无需重复设置

#### Scenario: 泄漏守护测试
- **WHEN** 合同测试执行真实流式调用序列后检查进程状态
- **THEN** litellm 全局线程池工作线程数与进程本地监听端口数保持稳定，进程可正常退出
