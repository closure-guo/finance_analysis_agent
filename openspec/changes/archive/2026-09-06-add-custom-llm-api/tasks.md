## 1. 后端 LLMConfig 数据结构

- [x] 1.1 创建 `LLMConfig` dataclass（model / base_url / api_key / thinking 四字段，均有默认值 None）
- [x] 1.2 创建 Pydantic 模型 `LLMConfigRequest`（用于 API 请求体反序列化），与 `LLMConfig` 字段一致
- [x] 1.3 编写单元测试：`LLMConfig` 默认值、`LLMConfigRequest` 从 JSON 反序列化、字段可选性

## 2. 后端管线链路配置注入

- [x] 2.1 修改 [llm.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/llm.py) `_build_kwargs`，新增 `llm_config` 参数，内部按优先级解析 model / base_url / api_key / thinking（请求配置 → 环境变量 → 默认值）
- [x] 2.2 修改 `call_llm` / `call_llm_stream` / `call_llm_with_tools` 三个入口函数签名，透传 `llm_config` 参数
- [x] 2.3 编写单元测试：`_build_kwargs` 在不同 `llm_config` 输入下生成正确的 kwargs（含 model 覆盖、base_url 覆盖、thinking 开关、api_key 回退链）
- [x] 2.4 编写单元测试：`llm_config=None` 时 `_build_kwargs` 输出与现有行为完全一致（回归测试）

## 3. 后端 ReAct 链路配置注入

- [x] 3.1 修改 [harness/litellm_client.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py) `LiteLLMClient.__init__`，新增 `thinking` 参数
- [x] 3.2 修改 `LiteLLMClient._build_kwargs`，根据构造时传入的 `thinking` 值决定 DeepSeek extra_body 设置（替代当前硬编码 `"enabled"`）
- [x] 3.3 修改 [agent_factory.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py) `build_agent`，新增 `llm_config` 参数，解析后传入 `LiteLLMClient` 构造
- [x] 3.4 编写单元测试：`LiteLLMClient` 在不同 thinking 配置下生成正确的 `_build_kwargs` 输出

## 4. 后端 API 端点扩展

- [x] 4.1 修改 [api.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py) `AnalyzeRequest` 和 `ChatRequest`，新增可选字段 `llm_config: LLMConfigRequest | None = None`
- [x] 4.2 修改 `/api/analyze` 端点逻辑：从 `req.llm_config` 解析 `LLMConfig`，透传到 `build_agent` 和管线调用
- [x] 4.3 修改 `/api/chat` 端点逻辑：同上，透传到 `build_agent`
- [x] 4.4 修改 `_run_react_analysis` / `_run_chat_task` 等内部函数签名，透传 `llm_config`
- [x] 4.5 确保顶层 `api_key` 与 `llm_config.api_key` 合并逻辑：`llm_config.api_key` 优先，其次顶层 `api_key`，最后环境变量
- [x] 4.6 新增 `GET /api/llm-config` 端点，返回后端默认配置（model / base_url / thinking，不含 api_key）
- [x] 4.7 新增 `POST /api/llm-config/models` 端点，接受 base_url + api_key，后端调用 `GET {base_url}/models` 拉取模型列表返回；端点不支持时返回空列表 + 错误提示
- [x] 4.7a 决策 A：模型发现端点 base_url 为空时**不回退**环境变量 `LLM_BASE_URL`（返回提示"请先配置 API Base URL 再刷新模型列表"）；`api_key` 仍可回退环境变量；分析链路 `call_llm` 回退行为不变
- [x] 4.8 新增 `POST /api/llm-config/test` 端点，接受完整 `llm_config`，后端发送极简 LLM 请求（`max_tokens=1`），返回 success / latency_ms / error / error_type
- [x] 4.9 编写集成测试：`/api/analyze` 和 `/api/chat` 携带 `llm_config` 时不报错，不携带时行为不变
- [x] 4.10 编写集成测试：`GET /api/llm-config` 返回正确的默认配置且不含 api_key
- [x] 4.11 编写集成测试：`POST /api/llm-config/models` 成功返回模型列表、base_url 不支持时返回空列表、base_url 为空时提示配置且不回退环境变量（决策 A）
- [x] 4.12 编写集成测试：`POST /api/llm-config/test` 成功返回 latency、失败返回正确 error_type（auth / network / model_not_found）

## 5. 前端设置面板

- [x] 5.1 将 [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) `ApiKeyModal` 扩展为 `SettingsModal`，新增模型名称、API Base URL、思考模式 Toggle 三项输入
- [x] 5.2 新增 localStorage key `fa_llm_config` 存储配置（JSON 序列化），从旧 key `fa_api_key` 自动迁移
- [x] 5.3 新增前端 API 调用 `GET /api/llm-config`，获取后端默认配置用于输入框 placeholder
- [x] 5.4 修改 `/api/chat`、`/api/analyze` 请求提交逻辑，将 localStorage 中的 LLM 配置组装为 `llm_config` 字段随请求发送
- [x] 5.5 确保思考模式 Toggle 仅在模型名包含 "deepseek" 时展示（非 DeepSeek 模型自动隐藏该开关）

## 6. 前端 Provider 预设与模型发现

- [x] 6.1 在 `SettingsModal` 顶部新增 Provider 预设选择器（Select），内置静态预设常量（DeepSeek 官方 / OpenAI / Anthropic / 本地 Ollama / 自定义）
- [x] 6.2 实现预设选择联动：选择预设后自动填充 model + base_url + thinking 默认值；用户手动修改后预设切换为 "自定义"
- [x] 6.3 在 model 输入框旁新增"刷新模型列表"按钮，点击后调用 `POST /api/llm-config/models` 拉取模型
- [x] 6.4 将返回的模型列表渲染为下拉选择，用户选择后自动拼接 litellm 前缀（如 `deepseek/`）填入 model 输入框
- [x] 6.5 模型发现失败时（空列表或错误）展示提示信息但不阻塞手动输入

## 7. 前端连通性测试

- [x] 7.1 在 `SettingsModal` 底部新增"测试连接"按钮，点击后调用 `POST /api/llm-config/test` 发送当前配置
- [x] 7.2 测试成功时展示绿色成功状态 + 响应延迟（毫秒）
- [x] 7.3 测试失败时展示红色失败状态 + 根据 error_type 展示针对性提示（auth → "API Key 无效" / network → "无法连接，请检查 Base URL" / model_not_found → "模型不存在" / unknown → 通用错误）
- [x] 7.4 测试请求进行中展示 loading 状态，防止重复点击

## 8. 管线深层调用链透传

- [x] 8.1 排查 `_run_deep_analysis` → 5 层管线节点 → `call_llm_stream` 的完整调用链，确保 `llm_config` 能透传到每个 `call_llm*` 调用
- [x] 8.2 排查 `nodes/_llm_utils.py` 的 `call_llm_streaming` 封装，新增 `llm_config` 透传参数
- [x] 8.3 编写单元测试：管线节点在 `llm_config` 注入下使用正确模型（mock litellm.completion 验证传入的 model 参数）

## 9. E2E 测试与验证

- [x] 9.1 编写 E2E 测试：前端设置面板中修改模型名称，提交分析请求，验证后端使用自定义模型（需 `TESTING=1` + stub 场景适配）
- [x] 9.2 编写 E2E 测试：设置面板配置持久化——刷新页面后配置仍在
- [x] 9.3 编写 E2E 测试：不配置任何 LLM 设置（localStorage 为空）时，分析/聊天行为与现有完全一致（回归）
- [x] 9.4 编写 E2E 测试：选择 Provider 预设后输入框自动填充正确值
- [x] 9.5 编写 E2E 测试：点击"测试连接"按钮后展示成功或失败状态
- [x] 9.6 手动验证：使用真实 LLM（非 TESTING 模式）验证自定义 model + base_url 生效，在 Langfuse trace 中确认模型名（2026-09-06：阿里云 MaaS deepseek-v4-flash-0731 实测，Langfuse generation.model 确认；连带修复 quick 通道 llmConfig 不透传缺陷 commit f0e4d29）
- [x] 9.7 落人工验证报告到 `tests/validation/`（tests/validation/2026-09-06-add-custom-llm-api-validation.md）

## 10. 前端多配置管理（profiles，方案 A）

- [x] 10.1 在 [llmConfig.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/llmConfig.ts) 新增 `LLMProfile` 类型（id / name / config）与 `fa_llm_profiles` localStorage 读写函数（getProfiles / saveProfiles / activateProfile / deleteProfile / getActiveConfig）
- [x] 10.2 实现旧 key 迁移：`getLlmConfig()` 在 `fa_llm_profiles` 不存在或为空时读取旧 key `fa_llm_config`，迁移为第一个 profile（名称「旧配置」）并激活，迁移后清除旧 key
- [x] 10.3 设置面板新增「配置管理」区：另存为输入框 + 保存按钮（名称为空时不保存并提示）+ profile 列表（名称 / 激活标记 / 删除按钮）
- [x] 10.4 删除 profile 时回退逻辑：删除激活项自动激活剩余第一个；删除最后一个后无可用配置，前端拦截并引导配置（后端环境变量回退保留）
- [x] 10.5 修改请求提交逻辑：`/api/chat`、`/api/analyze` 的 `llm_config` 字段改从激活 profile 读取（替代直接读 `fa_llm_config`）
- [x] 10.6 编写单元测试：profiles 增删改查、切换激活并持久化、旧 `fa_llm_config` 迁移、无 profile 时回退默认配置

## 11. 前端 LLM 切换下拉框

- [x] 11.1 在 `EmptyState` 模式选择器（"模式："下拉）右侧新增 LLM 切换下拉框，显示当前激活 profile 名，点击展开列出全部 profile，选中即切换 activeId 并持久化
- [x] 11.2 在 `ChatInputBar` 模式切换旁新增同样的 LLM 切换下拉框
- [x] 11.3 无任何 profile 时下拉框显示"未配置"，点击引导打开设置面板；下拉框与设置面板共享同一 `fa_llm_profiles` 数据源，切换即时反映

## 12. 多配置 E2E 测试与验证

- [x] 12.1 编写 E2E 测试：设置面板另存为两个命名 profile → LLM 下拉框列出并可切换 → 提交分析请求验证携带对应配置
- [x] 12.2 编写 E2E 测试：旧 `fa_llm_config` 自动迁移为「旧配置」profile，下拉框正确显示
- [x] 12.3 编写 E2E 测试：删除激活 profile 自动回退到剩余第一个；删除最后一个后无可用配置时前端拦截并引导配置
- [x] 12.4 运行全量前端测试 + E2E，确认无回归

## 13. 强制配置（删除隐式默认配置）

- [x] 13.1 前端删除「默认配置」隐式可用概念：无 profile 时 LLM 下拉框显示"未配置"而非"默认配置"；迁移 profile 名称改为「旧配置」；确认保存自动创建名称改为「我的配置」
- [x] 13.2 拦截无配置发送：`ChatInputBar` 与 `EmptyState` 在激活配置无 apiKey 时阻止发送并自动打开设置面板（键盘回车与发送按钮两条路径）
- [x] 13.3 无 profile 时点击 LLM 下拉框引导打开设置面板（EmptyState 与 ChatInputBar 两处）
- [x] 13.4 保留后端环境变量回退（`LLM_MODEL`/`LLM_API_KEY` 等），确保后端测试与 CI 不受影响
- [x] 13.5 更新单元测试断言（迁移名「旧配置」、无 profile 显示「未配置」）与 E2E 断言，运行全量验证

> 注：9.1-9.5 E2E 测试已编写于 `tests/e2e/test_llm_config_settings.py` 并通过
> （`uv run python tests/e2e/test_llm_config_settings.py` → ALL LLM CONFIG E2E CHECKS PASSED）。
> 12.1-12.3 E2E 测试已编写于 `tests/e2e/test_llm_profiles.py` 并通过
> （`uv run python tests/e2e/test_llm_profiles.py` → ALL LLM PROFILES E2E CHECKS PASSED）。
> 运行前置：`TESTING=1 uvicorn finance_agent.api:app --port 8000` + `npm run dev`。
