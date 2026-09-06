## Context

当前系统 LLM 配置完全通过环境变量实现（`LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_THINKING`、`LLM_REASONING_EFFORT`）。前端唯一的配置入口是 [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) 中的 `ApiKeyModal` 弹窗，仅收集 API Key 并随请求体发送。

后端有两条 LLM 调用链路：
- **管线链路**（[llm.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/llm.py)）：`call_llm` / `call_llm_stream` / `call_llm_with_tools` → `litellm.completion`，被 5 层分析流水线各节点使用。目前仅接受 `api_key` 参数，model / base_url / thinking 均从环境变量读取。
- **ReAct 链路**（[harness/litellm_client.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/litellm_client.py)）：`LiteLLMClient.chat_stream` → `litellm.acompletion`，被 [agent_factory.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py) `build_agent` 构建的 ReAct Agent 使用。目前仅接受 `model` + `api_key`，base_url 从环境变量读取。

用户无法在运行时切换模型、更改 API 端点或调整思考模式——必须重启服务修改环境变量。

## Goals / Non-Goals

**Goals:**

- 用户可在前端设置面板配置 model / base_url / api_key / thinking，配置持久化到 localStorage
- 后端按请求级别注入 LLM 配置，覆盖环境变量默认值
- 管线链路和 ReAct 链路都支持请求级配置注入
- 向后兼容：不传配置时行为与现有完全一致（环境变量默认值）

**Non-Goals:**

- 不做多用户/多租户 LLM 配置持久化（配置仅存浏览器 localStorage，后端不存储）
- 不做多配置的后端持久化与跨设备同步（多套 profile 存 localStorage，不上传后端；后续若需跨设备可加「导出/导入 JSON」）
- 不做模型预设/模型库管理（用户自行输入 litellm 格式模型名）
- 不做请求级 reasoning_effort / temperature / max_tokens 等细粒度参数暴露（后续可扩展）
- 不修改 Langfuse trace 行为（LLM 配置变更对 trace 透明）
- 不做多 API Key 轮询/负载均衡

## Decisions

### Decision 1: `LLMConfig` 数据结构统一传递

引入 `LLMConfig` dataclass 统一封装 4 个字段：

```python
@dataclass
class LLMConfig:
    model: str | None = None        # litellm 格式模型名
    base_url: str | None = None     # OpenAI 兼容端点
    api_key: str | None = None      # API Key
    thinking: str | None = None     # "enabled" | "disabled"
```

**理由**：相比逐参数传递，结构体封装避免函数签名膨胀（管线链路 `call_llm` 已有 7 个参数），且后续扩展（reasoning_effort 等）只需加字段不改签名。

**备选方案**：使用 contextvar 全局传递——被否决，因为管线链路有 4 路并行分析师（asyncio.gather），contextvar 在并行场景下传播语义复杂，显式参数传递更安全可测试。

### Decision 2: 配置解析优先级（覆盖链）

每个字段的解析顺序：**请求体 `llm_config` → 环境变量 → 内置默认值**

```python
def resolveModel(reqConfig: str | None) -> str:
    return reqConfig or os.getenv("LLM_MODEL", _DEFAULT_MODEL)
```

**理由**：向后兼容——未传 `llm_config` 时完全回退到现有行为。不需要迁移。

### Decision 3: API 契约扩展（非破坏性）

`AnalyzeRequest` 和 `ChatRequest` 新增可选字段 `llm_config`：

```python
class LLMConfigRequest(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None      # 与顶层 api_key 合并（llm_config.api_key 优先）
    thinking: str | None = None

class AnalyzeRequest(BaseModel):
    ...  # 现有字段不变
    llm_config: LLMConfigRequest | None = None  # 新增可选字段
```

新增端点 `GET /api/llm-config`，返回环境变量默认配置（model / base_url / thinking），供前端展示占位符。

**理由**：非破坏性扩展——现有 API 调用方不受影响。

### Decision 4: 前端设置面板替换 ApiKeyModal

将 `ApiKeyModal` 扩展为 `SettingsModal`，包含：
- API Key 输入（保留现有行为）
- 模型名称输入（placeholder 从 `/api/llm-config` 获取）
- API Base URL 输入（placeholder 同上）
- 思考模式开关（Toggle：enabled / disabled）

配置持久化到 localStorage key `fa_llm_config`（JSON 序列化）。每次请求携带 `llm_config` 字段。

**理由**：扩展现有组件而非新建，保持 UI 入口一致性（header 齿轮按钮 → 设置面板）。

### Decision 5: Provider 预设快捷填充（借鉴 cc-switch）

设置面板顶部提供 Provider 预设下拉（Select），内置以下预设（静态定义在前端代码中）：

| 预设名称 | model 填充 | base_url 填充 | thinking 默认 |
|---------|-----------|--------------|--------------|
| DeepSeek 官方 | `deepseek/deepseek-chat` | `https://api.deepseek.com/v1` | enabled |
| OpenAI | `openai/gpt-4o` | （留空，litellm 自动路由） | — |
| Anthropic | `anthropic/claude-sonnet-4-20250514` | （留空） | — |
| 本地 Ollama | `openai/llama3` | `http://localhost:11434/v1` | — |
| 自定义 | （留空） | （留空） | enabled |

用户选择预设后，model / base_url 输入框自动填充（用户仍可手动修改）。选择预设不触发保存，仅做快捷填充。

**理由**：借鉴 cc-switch 的 50+ provider presets 设计。我们不维护完整预设库（过重），仅内置 4 个高频预设 + 自定义入口。预设数据是前端静态常量，不需后端端点。

**备选方案**：后端维护预设库 → 被否决，预设数据变更频率极低，前端硬编码更简单且零延迟。

### Decision 6: 模型自动发现（借鉴 cc-switch v3.13）

新增后端端点 `POST /api/llm-config/models`，接受 `base_url` + `api_key`（均可选，回退环境变量），后端调用 `GET {base_url}/models`（OpenAI 兼容模型列表端点）拉取可用模型，返回模型 ID 列表。

```python
# POST /api/llm-config/models 请求体
{
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "sk-xxx"
}

# 响应
{
  "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]
}
```

前端在设置面板提供"刷新模型列表"按钮，调用该端点后将返回的模型列表渲染为下拉选择（<select>），用户从中选择后自动拼接 litellm 前缀（如 `deepseek/`）填入 model 输入框。

**理由**：模型发现由后端代理调用（而非前端直接调），因为：
1. 避免 CORS 问题（多数 LLM API 不允许浏览器跨域访问）
2. api_key 不暴露在前端网络请求中（经后端中转，不记录日志）

**备选方案**：前端直接调 `/v1/models` → 被否决（CORS + 安全）。

**错误处理**：
- base_url 不支持 `/models` 端点（如部分 Anthropic API）时，返回空列表 + 错误提示，不影响手动输入。
- **base_url 为空时（决策 A 修订）**：**不回退**环境变量 `LLM_BASE_URL`，直接返回空列表 + "请先配置 API Base URL 再刷新模型列表"。原因：模型发现是「探测用户指定端点」的工具，回退环境端点会悄悄返回该端点模型列表，违背用户直觉（如"自定义"预设 base_url 为空时，用户期望提示配置，而非看到环境端点的一堆模型）。该回退阻断**仅限**模型发现端点；分析链路 `call_llm` 的回退（请求配置 → 环境变量 → 默认值）保持不变。`api_key` 仍允许回退环境变量（用户可能只填 base_url 想探测端点，密钥用已配置的）。

### Decision 7: 连通性测试（借鉴 cc-switch）

新增后端端点 `POST /api/llm-config/test`，接受完整 `llm_config`（model / base_url / api_key / thinking），后端用该配置发送一个极简 LLM 请求（`max_tokens=1`，prompt="Hi"），返回测试结果：

```python
# 响应
{
  "success": true,
  "latency_ms": 342,
  "model": "deepseek/deepseek-chat"
}
# 或
{
  "success": false,
  "error": "AuthenticationError: Invalid API key",
  "error_type": "auth"
}
```

前端设置面板提供"测试连接"按钮，展示成功（绿色 + 延迟）或失败（红色 + 错误信息）。

**理由**：借鉴 cc-switch 的 health check。测试请求由后端发送（非前端直连），同样规避 CORS 和密钥暴露问题。

**错误分类**：`auth`（认证失败）、`network`（连接超时/不通）、`model_not_found`（模型不存在）、`unknown`（其他），便于前端展示针对性提示。

**备选方案**：测试时仅校验 API key 格式 → 被否决，格式校验无法发现 base_url 错误或模型名拼写错误。

### Decision 8: 管线链路配置注入点

[llm.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/llm.py) 的 `_build_kwargs` 新增 `llm_config: LLMConfig | None = None` 参数。三个入口函数（`call_llm` / `call_llm_stream` / `call_llm_with_tools`）透传该参数。配置在 `_build_kwargs` 内部解析：

```python
def _build_kwargs(..., llm_config: LLMConfig | None = None):
    cfg = llm_config or LLMConfig()
    model = cfg.model or os.getenv("LLM_MODEL", _DEFAULT_MODEL)
    base_url = cfg.base_url or os.getenv("LLM_BASE_URL", "")
    thinking = cfg.thinking or os.getenv("LLM_THINKING", "enabled")
    ...
```

[agent_factory.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/agent_factory.py) `build_agent` 接受 `llm_config` 参数，构建 `LiteLLMClient` 时注入 model / api_key / base_url。

`_run_deep_analysis` 闭包内的管线调用通过 `llm_config` 参数透传到 `call_llm_stream`。

### Decision 9: ReAct 链路配置注入点

`LiteLLMClient.__init__` 已支持 `model` / `api_key` / `base_url` 参数。`build_agent` 在构建时将解析后的配置传入。`LiteLLMClient._build_kwargs` 中的 thinking 设置改为接受构造时传入的 thinking 值。

### Decision 10: 多配置管理（方案 A：localStorage profiles）

引入多套命名 LLM 配置（profile），存浏览器 localStorage，后端不存储：

```typescript
// llmConfig.ts 新增
interface LLMProfile {
  id: string        // 唯一 ID（Date.now().toString()）
  name: string      // 用户命名，如「DeepSeek 办公」
  config: LLMConfig // { model, baseUrl, apiKey, thinking }
}
// localStorage key: fa_llm_profiles
// { profiles: LLMProfile[], activeId: string }
```

- **读取**：`getLlmConfig()` 返回 `activeId` 对应 profile 的 config；`fa_llm_profiles` 不存在或为空时回退读取旧 key `fa_llm_config`（自动迁移为第一个 profile，name「旧配置」）
- **写入**：设置面板「另存为」将当前表单配置命名为新 profile 追加；切换 activeId 持久化；删除 profile 后若删除的是当前激活项，自动激活剩余第一个；删除最后一个后无可用配置，前端拦截并引导配置（后端环境变量回退保留）
- **强制配置**：前端删除「默认配置」隐式可用概念——无 profile 时下拉框显示"未配置"，发送分析/聊天被拦截并自动打开设置面板；用户保存配置后创建第一个 profile（确认保存自动命名「我的配置」）方可使用
- **请求携带**：`/api/chat`、`/api/analyze` 请求体 `llm_config` 字段值来自激活 profile 的 config（替代直接读 `fa_llm_config`）
- **设置面板**：新增「配置管理」区——「另存为」输入框 + 保存按钮 + 已存 profile 列表（每项含激活标记、删除按钮）

**理由**：对比后端 SQLite 方案（Decision 10 备选），localStorage 方案胜出：
1. **安全**：api_key 是敏感凭证，存 localStorage 只在本机；存后端 SQLite 明文集中存储，泄露面大
2. **YAGNI**：单用户本地工具（单 worker + 进程内 StreamRegistry），无多设备/多用户共享需求
3. **改动量**：纯前端，与现有 `fa_llm_config` 模式一致；后端零改动、零迁移
4. **兜底**：未来若需跨设备，加「导出/导入 JSON」即可（仍纯前端）

**备选方案（B）**：后端 SQLite `llm_profiles` 表 + CRUD 端点 → 被否决，理由同上（apiKey 集中存储安全风险、单用户无共享需求、全栈改动量大）。

### Decision 11: LLM 切换下拉框

在**模式选择器（快速模式/深度研究）右侧**新增 LLM 切换下拉框，两处位置：

| 位置 | 文件 | 行为 |
|------|------|------|
| EmptyState（空闲首页） | [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) `EmptyState`（"模式："下拉右侧） | 点击展开 profile 列表，选中即切换 activeId 并持久化 |
| 聊天输入区 | `ChatInputBar`（模式切换旁） | 同上 |

- 下拉框 SHALL 显示当前激活 profile 名（无 profile 时显示"未配置"，点击引导打开设置面板）
- 选中 profile 后 SHALL 立即生效：后续 `/api/chat`、`/api/analyze` 请求携带新激活配置
- 下拉框与设置面板的「配置管理」区共享同一 `fa_llm_profiles` 数据源，切换即时反映

**理由**：模式选择器是用户每次使用都会看到的控件，LLM 切换放在其右侧符合「配置入口集中、可见性高」的原则，用户无需打开设置面板即可切换模型。

## Risks / Trade-offs

- **[风险] 用户输入错误的 model/base_url 导致 LLM 调用失败** → 连通性测试功能（Decision 7）让用户在保存前验证配置；后端返回 LLM API 错误时，前端在 SSE 错误事件中展示友好提示
- **[风险] localStorage 配置与多人共享浏览器冲突** → Non-Goal，当前是单用户场景；后续可考虑后端持久化
- **[权衡] 每次请求携带 llm_config 增加请求体大小** → 增量约 200 字节，可忽略
- **[风险] 管线链路 4 路并行分析师共享同一 LLMConfig** → 设计正确行为——同一分析请求应使用同一模型，无需按分析师差异化配置
- **[风险] base_url 注入的安全风险（SSRF）** → base_url 仅传给 litellm 的 `api_base` 参数（litellm 内部用 httpx 发起请求），不做服务端转发；且用户配置自己的 base_url（非他人注入），风险等同于用户自行设置环境变量
- **[风险] 模型自动发现端点 `/models` 不可用（如 Anthropic）** → 返回空列表 + 错误提示，不影响手动输入；非阻塞降级
- **[风险] 连通性测试消耗少量 token** → 测试请求 `max_tokens=1`，消耗极低（约 2-3 token）；用户主动点击触发，非自动执行
- **[风险] profile 中 apiKey 存 localStorage 的泄露面** → 与现有 `fa_llm_config` 一致，仅本机浏览器；相比后端 SQLite 明文集中存储泄露面更小；浏览器清理数据会丢失 profile，属可接受的本地工具局限
- **[风险] 多 profile 与多人共享浏览器冲突** → 同 localStorage 冲突场景，Non-Goal，当前单用户场景；后续可加「导出/导入 JSON」备份
- **[风险] 删除激活 profile 导致配置失效** → 设计已覆盖：删除当前激活项时自动激活剩余第一个；删除最后一个后无可用配置时前端拦截并引导配置（不静默走环境变量，避免用户误以为已配置）
