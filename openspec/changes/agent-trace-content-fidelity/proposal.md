## Why

Langfuse tracing 的节点骨架已覆盖 5 层管线 16 个 Agent span（ADR-0015），事故复盘时却"看得到节点、看不到因果"：

- LLM 真实推理过程（`reasoning_content`）不入 trace —— DeepSeek 思考链流式下发到前端后即丢弃，`litellm_client.py` 的 `_finish_langfuse` 与 `llm.py` 的 `_gen.update(output=...)` 都不收 reasoning，复盘时无法回答"Agent 为什么这样决策"。
- 工具调用决策（`tool_calls`）不写 generation output —— `litellm_client.py:230-248` 的 `_finish_langfuse` 只传 answer 文本，LLM 决定调用什么工具的原始结构化字段在 trace 里看不到，只能从下游 `tool:{name}` span 反推。
- `prompt_name` / `prompt_version` 未挂 generation —— ADR-0015 第 24 行明确承诺"Generation 附带 prompt_name + prompt_version (ADR-0016)"，`llm.py` 三入口（`:180/256/344`）至今未实现，prompt 迭代追溯不可达。
- AKShare 取数链路零 span —— `nodes/fetch.py:121-249` 的 20+ 个取数调用全部裸跑，失败仅 `logger.warning`；incident 008（AKShare 卡死）复盘时 trace 只看到 `fetch_data` span 一直挂着，看不到具体哪个子调用卡住。
- 解析降级与重试静默发生 —— `analysts.py` 的 `parse_degraded` / `_sanitize_claims` 改写、`loop.py` 的空输出重试 / DSML 防御性解析，仅 `logger.warning`，不上 trace；事故时不知 prompt 与代码枚举已不一致。

观测盲区集中在"节点内部内容保真度"。补埋点让 trace 能回答"Agent 为什么这样决策"，且为 Judge 评估体系（delta `agent-evaluation-suite`）提供完整输入。

## What Changes

1. **LLM generation 落 `reasoning_content`** —— 流式累加 DeepSeek 思考链，写入 generation output，与 answer 文本并列。
2. **LLM generation 落 `tool_calls`** —— 工具调用决策（工具名 + arguments）写入 generation output，不再只记 answer 文本。
3. **LLM generation 挂 prompt 元数据** —— `prompt_name` + `prompt_version` 写入 generation metadata（兑现 ADR-0015 第 24 行承诺），版本来自 `prompts/loader.py` 的 Langfuse production label。
4. **数据源调用 span 可观测** —— AKShare 等外部取数经 `open_span("data_source:{name}")` 包裹，记录入参 / 返回摘要 / 耗时，失败标 `level="ERROR"`。
5. **降级与重试路径 span 可观测** —— 解析降级（`parse_degraded`）、枚举兜底改写（`_sanitize_claims`）、空输出重试、纯文本无工具调用重试、DSML 防御性解析，上 span metadata（事件类型 + 计数 + 原始片段）+ level。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `trace-observability`：追加 5 条 requirement（LLM 推理内容可观测 / LLM 工具调用决策可观测 / LLM Generation Prompt 元数据可追溯 / 数据源调用 span 可观测 / 降级与重试路径 span 可观测）。**不修改现有 4 条 requirement**（工具调用 span / 网络搜索 span / `open_span` 优雅降级 / span 不改变业务行为），纯 ADDED，与并行 delta 零 textual 冲突，可任意顺序 sync。

## Impact

- **源码**：`src/finance_agent/llm.py`（`call_llm` / `call_llm_stream` / `call_llm_with_tools` 的 generation output 与 metadata）、`src/finance_agent/harness/litellm_client.py`（`_accumulated_reasoning` + `_finish_langfuse`）、`src/finance_agent/harness/loop.py`（重试 / DSML 解析 span metadata）、`src/finance_agent/nodes/fetch.py`（AKShare 取数 `open_span`）、`src/finance_agent/nodes/analysts.py`（`parse_degraded` / `_sanitize_claims` span metadata）。
- **可观测性**：Langfuse trace 内容完整度提升；`langfuse-llm-as-a-judge` 环境的裁判调用不受影响（裁判不经 LLM generation 入口）。
- **依赖**：与 `enable-deepseek-thinking-mode` 协调 —— reasoning 落 trace 依赖 thinking 模式已开启（该 delta task 1.2 已完成 `litellm_client.py:92` 的 `extra_body`），本 delta 只补"落 trace"，不动 thinking 开关。
- **协调**：与 `transparent-system-events`（规则层 span）无重叠，各自独立 requirement；与 `harden-llm-output-validation` 无重叠（该校验 schema，本 delta 只补观测埋点，不改校验行为）。
- **风险**：中 —— 埋点改动面广（5 文件），但均为"只增不改业务行为"，且全部经 `open_span` / `update_current` 的优雅降级路径兜底（未配置 Langfuse 时 no-op），不引入新异常路径。`tool_calls` / `reasoning` 写入 output 需注意大体积 span 的序列化成本（对策见 design）。
