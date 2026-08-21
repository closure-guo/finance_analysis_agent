# Design: add-llm-api-form

## Approach

在既有 `llm-config` 链路新增 `apiForm` 字段，并新增裸模型名前缀推导，两者协同，全程透传、不在业务代码引入 provider 分支：

1. **前端**：`LLMConfig` 新增 `apiForm?: string`（取值枚举 `chat_completion` / `messages` / `responses`，空为未设置）。`SettingsModal` 在「Provider 预设」下方新增「API 形式」下拉框（选项带 OpenAI / Anthropic 字样：OpenAI Chat Completion / Anthropic Messages / OpenAI Responses）。`applyPreset` 中预设可携带对应 `apiForm`（OpenAI 系→`chat_completion`、Anthropic→`messages`）。`buildLlmConfigPayload` 仅在显式设置时携带 `apiForm`，并在请求前执行前缀推导。

2. **前缀推导**（前端收口，provider 判定只发生一次）：构建生效模型名时，若模型名不含 `/`，按 `apiForm` 推导补全前缀——`chat_completion`/`responses`→`openai`、`messages`→`anthropic`；模型名已含 `/` 则原样使用；`apiForm` 为空则不推导原样下发。推导结果作为请求模型名发送，后端照常按 litellm 模型名处理。

3. **请求契约**：`LLMConfigRequest` 新增可选 `apiForm`，用 `Literal`/枚举声明三个合法值 + 校验器拒绝非法值（对标 `contextLength` 的 422 拒绝语义）；`_to_llm_config` 透传。

4. **后端消费**：请求级配置解析进 `ModelProfile` 后，gateway 构建请求 kwargs 时把 `apiForm` 映射为 litellm `api` 参数（`chat_completion→"chat"`、`messages→"messages"`、`responses→"responses"`）。空值不设置 `api`，litellm 按 model 前缀自动路由，保证与现状完全一致。

映射与推导都收敛在单一消费者处（前端 payload 构建 + 后端 adapter/gateway），延续设计档案 §7 的「provider 细节只发生在 adapter」原则。

## Alternatives Considered

- **方案 A：仅前端透传 model，不新增 apiForm / 不推导前缀** —— 无法覆盖「同一形式的端点想换协议」与「用户不想手写前缀」两个诉求。不选。
- **方案 B：后端按 model 前缀硬编码推断协议与前缀** —— 引入隐性分支，用户无法显式覆盖，违背「显式选择」目标。不选。
- **方案 C：前缀推导放后端** —— 后端无法可靠知道「用户是否故意省略前缀」，且需要重复 model 解析逻辑；收敛在前端更直接。不选。

## Risks

- **litellm `api` 参数兼容性**：不同 litellm 版本对 `api="messages"` / `api="responses"` 支持可能不同。对策：透传前确认运行版本支持；非法/不支持时按现状透传并由端点显式报错，不吞错。
- **裸模型名推导歧义**：DeepSeek 等复用 Chat Completion 协议但需自有前缀的 provider，其预设已携带完整前缀（`deepseek/deepseek-chat`），规则「已含 `/` 则原样使用」可兜底；推导仅在裸名且已选 API 形式时触发。
- **旧配置兼容**：存量 profile 无 `apiForm` 且模型名已带前缀，读取时视为未设置、原样使用，无需迁移脚本。
