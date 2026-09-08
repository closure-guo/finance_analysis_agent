## Context

当前系统在 `harness/litellm_client.py` 第 83-90 行显式禁用 DeepSeek 原生思考模式：

```python
# DeepSeek: harness 自己管理思考过程，始终禁用原生 thinking mode
# （thinking mode 的 reasoning_content 与 tool calling 不兼容，
#   且多轮对话时历史消息缺少 reasoning_content 会导致 400 错误）
if is_ds:
    kwargs["temperature"] = temperature
    kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
```

该注释基于旧版 DeepSeek API 的限制。2025-12 起 DeepSeek 官方文档明确支持思考模式下的工具调用，仅要求：**工具调用轮次的 assistant 消息在后续请求中必须回传 `reasoning_content` 字段**。

### 现有"伪思考"机制

由于禁用了原生思考，harness loop 把 LLM 的 `text_delta`（普通文本输出）当作"思考"流式下发（`StreamEvent.think`），流末用 `thinking_to_answer` 通知前端把"思考"转为回答。这导致：
- LLM 一次性返回回答（如"沈阳天气"）时，思考=回答，`thinking_to_answer` 剥离后思考为空，横幅消失
- Langfuse trace 中无 `reasoning_content`，无法观察 LLM 真实推理

### DeepSeek 思考模式工作原理（官方文档）

- 开启后，响应中 `reasoning_content`（思维链）与 `content`（最终回答）同级但分离
- 流式输出顺序：先 `reasoning_content` delta，后 `content` delta
- 工具调用：思考模式支持多轮"思考 -> 工具调用 -> 再思考"
- **关键约束**：工具调用轮次的 `reasoning_content` 在后续所有请求中必须回传 API；非工具调用轮次的 `reasoning_content` 可不回传（API 忽略）
- 思考模式不支持 `temperature` / `top_p` 等参数（设置不报错但不生效）

### 现有架构关键点

- `LLMResponse`（`llm_client.py#L113`）：只有 `text_delta` / `tool_calls` / `is_finished`，无 `reasoning_delta`
- `Message`（`types.py#L77`）：只有 `role` / `content` / `tool_calls` / `tool_call_id`，无 `reasoning_content`
- `ContextManager.append_assistant`（`context.py#L125`）：不接收 `reasoning_content`
- harness loop 第 367-377 行：`chunk.text_delta` 触发 `StreamEvent.think`，无 `reasoning_content` 处理
- `ReplyCollector`（`api.py#L796`）：从 `thinking_token` / `thinking_to_answer` 收集 thinking，需改为直接收集 `reasoning_content`

## Goals / Non-Goals

**Goals:**

- 开启 DeepSeek 原生思考模式，LLM 产生独立 `reasoning_content` 思维链
- 前端展示真正的 LLM 推理过程（原生 reasoning），而非把回答文本当思考
- 工具调用轮次正确回传 `reasoning_content`，避免 400 错误
- Langfuse trace 中可观察 LLM 真实思考内容

**Non-Goals:**

- 不改动前端思考横幅的展示逻辑（四态、标题生成等已由 thinking-stream-banner-display delta 覆盖）
- 不改动思考内容持久化结构（仍存 `chat_history.thinking`，内容来源从 text_delta 改为 reasoning_content）
- 不改动 5 层分析管线节点的 LLM 调用（管线节点是独立 LLM 调用，非 ReAct harness 循环）
- 不支持 reasoning_effort 参数调节思考强度（默认 high，后续可扩展）

## Decisions

### 决策 1：开启思考模式，移除 disabled 配置

**选择**：`litellm_client.py` 中 `extra_body` 从 `{"thinking": {"type": "disabled"}}` 改为 `{"thinking": {"type": "enabled"}}`，并移除 `temperature` 参数（思考模式不支持）。

**理由**：DeepSeek 官方文档明确支持思考模式 + 工具调用，现有禁用基于过时信息。开启后 LLM 先输出 reasoning_content 再输出 content，天然分离思考与回答。

**替代方案**：保持禁用，继续用 text_delta 伪思考 -> 否决，违背用户诉求，且 Langfuse 无真实思考 trace。

### 决策 2：LLMResponse 新增 reasoning_delta 字段

**选择**：`LLMResponse`（`llm_client.py`）新增 `reasoning_delta: str = ""` 字段。`chat_stream` 解析 chunk 的 `delta.reasoning_content`，作为 `reasoning_delta` 流式下发，与 `text_delta`（content）分离。

**理由**：
- reasoning_content 与 content 是两个独立字段，分离下发让 harness loop 能区分"思考"与"回答"
- 前端可分别消费 reasoning（思考横幅）与 content（回答区），无需 `thinking_to_answer` 剥离

**替代方案**：复用 `text_delta` 携带 reasoning，用标记区分 -> 否决，破坏语义清晰性，且 harness 需解析标记。

### 决策 3：harness loop 事件来源调整

**选择**：
- `reasoning_delta` -> `StreamEvent.think`（思考横幅消费）
- `text_delta` -> `StreamEvent.answer`（回答区消费，新增 ANSWER 事件类型，或复用现有 ANSWER）
- **移除 `thinking_to_answer` / `THINK_TO_ANSWER` 逻辑**：reasoning 与 content 天然分离，无需剥离
- **移除 `thinking_replace` / `THINK_REPLACE`**：reasoning_content 是 LLM 原生输出，无需 DSML 清理后处理

**理由**：原生思考模式下 reasoning 与 content 天然分离，现有"流式当思考再剥离"的机制是禁用思考模式的产物，开启原生思考后应移除。

**替代方案**：保留 `thinking_to_answer` 作为兜底 -> 否决，reasoning 与 content 分离后剥离逻辑无意义且增加复杂度。

### 决策 4：Message 新增 reasoning_content 字段，工具调用轮次回传

**选择**：
- `Message`（`types.py`）新增 `reasoning_content: str | None = None` 字段
- `to_api_dict()`：当 `reasoning_content` 非空且 `tool_calls` 非空时，输出 `reasoning_content` 字段（工具调用轮次必须回传）
- 非工具调用轮次不输出 `reasoning_content`（API 忽略，减少 token）
- `ContextManager.append_assistant` 新增 `reasoning_content` 参数，存储到 Message

**理由**：DeepSeek 官方要求工具调用轮次的 assistant 消息必须回传 `reasoning_content`，否则 400 错误。非工具调用轮次不回传以节省 token。

**替代方案**：所有轮次都回传 reasoning_content -> 否决，非工具调用轮次 API 忽略该字段，浪费 token。

### 决策 5：SSE 事件复用 thinking_token，新增 reasoning 完成标记

**选择**：
- 后端 `agent_factory.py` 中 `reasoning_delta` 下发为 `thinking_token` 事件（复用现有事件，前端无需改消费逻辑）
- `text_delta` 下发为 `chat_token` 事件（现有 ANSWER -> chat_token）
- 移除 `thinking_to_answer` / `thinking_replace` 事件下发
- 流式结束时 `chat_done` 仍触发思考横幅完成态

**理由**：复用 `thinking_token` 事件让前端思考横幅消费逻辑（thinking-stream-banner-display delta 的成果）无需改动，最小化前端变更。

### 决策 6：ReplyCollector 直接收集 reasoning_content

**选择**：`ReplyCollector`（`api.py`）新增 `reasoning` 字段，从 `LLMResponse.reasoning_delta` 累积 reasoning_content，持久化到 `chat_history.thinking`（复用现有字段）。

**理由**：持久化结构不变（仍是 `thinking` 字段），但内容来源从"text_delta 推断"改为"reasoning_content 直接收集"，数据更准确。

## Risks / Trade-offs

- **[思考模式不支持 temperature]** 思考模式下 temperature/top_p 等参数不生效 -> 可接受，思考模式由 reasoning_effort 控制强度，默认 high 已够用
- **[reasoning_content token 消耗]** 思考内容额外消耗输出 token -> 可接受，DeepSeek 定价已含 reasoning token；可通过 reasoning_effort 调节
- **[多轮工具调用回传复杂度]** 工具调用轮次必须回传 reasoning_content，ContextManager 压缩时需保留 -> L2 压缩策略需调整，不能删除带 tool_calls 的 assistant 消息的 reasoning_content
- **[模型兼容性]** 仅 DeepSeek 支持思考模式，其他模型（如 OpenAI）无 reasoning_content -> LLMClient 需条件判断，非 DeepSeek 保持现有 text_delta 行为
- **[回归风险]** 移除 `thinking_to_answer` 影响前端现有剥离逻辑 -> 前端需同步移除 `thinking_to_answer` 处理，reasoning 与 content 天然分离后无需剥离

## Migration Plan

- 后端：
  1. `LLMResponse` 新增 `reasoning_delta` 字段
  2. `Message` 新增 `reasoning_content` 字段，`to_api_dict()` 工具调用轮次输出
  3. `ContextManager.append_assistant` 接收 `reasoning_content`
  4. `LiteLLMClient.chat_stream` 开启思考模式，解析 `reasoning_content` delta
  5. harness loop：`reasoning_delta` -> THINK，`text_delta` -> ANSWER，移除 `thinking_to_answer` / `thinking_replace`
  6. `agent_factory.py`：`reasoning_delta` 下发 `thinking_token`，`text_delta` 下发 `chat_token`，移除 `thinking_to_answer` 下发
  7. `ReplyCollector` 收集 `reasoning_content` 到 thinking
  8. `StubLLMClient` 模拟 reasoning_content 输出
- 前端：
  1. 移除 `thinking_to_answer` / `thinking_replace` 事件处理（reasoning 与 content 天然分离）
  2. `thinking_token` 消费逻辑不变（复用 thinking-stream-banner-display 成果）
- 回滚：还原 `litellm_client.py` 的 `disabled` 配置 + 还原 harness loop 的 text_delta->THINK 逻辑

## Open Questions

- reasoning_effort 是否需要可配置（环境变量）？倾向：先默认 high，后续按需扩展
- 思考模式下非 DeepSeek 模型的行为？倾向：LLMClient 基类不处理 reasoning，仅 DeepSeek 子类解析
- ContextManager L2 压缩"删除过期 think 消息"逻辑是否需调整？倾向：现有逻辑删除 `<thinking>` 标记的旧消息，开启原生思考后 assistant 消息含 reasoning_content 字段，L2 需改为清理非工具调用轮次的 reasoning_content 以节省 token
