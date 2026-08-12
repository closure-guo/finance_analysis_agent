## Context

### 现状

Langfuse 双机制集成（ADR-0015）：CallbackHandler 管 5 层管线骨架 span，`start_as_current_observation` 管 LLM generation。骨架层覆盖到位，generation 层与节点内部子操作层存在内容保真度缺口。

- **generation output 不完整**：`harness/litellm_client.py:165` 的 `_accumulated_text` 只收 answer 文本；`_finish_langfuse`（`:230-248`）的 `text` 参数不含 `reasoning_content`（流式 yield 出去即丢弃），不含 `tool_calls`（解析后未回写）。`llm.py:268` 的 `_accumulated` 同样只收 answer，`:291` `_gen.update(output=_accumulated)`。
- **prompt 元数据缺失**：`llm.py:180/256/344` 三入口的 generation name 都是 `f"litellm:{model}"`，未挂 `prompt_name` / `prompt_version`。`prompts/loader.py:38-50` 已能从 Langfuse production label 拿到版本，但版本号未透传到 generation。
- **数据源子操作无 span**：`nodes/fetch.py:121-249` 的 AKShare 调用（三大报表 / 行情 / K 线 / 行业 / 宏观 / 新闻 / 同业 / 季度）全部裸跑，失败 `logger.warning` 不上 trace。
- **降级路径隐形**：`analysts.py:60-86` 的 `parse_degraded=True` 与 `:33-57` 的 `_sanitize_claims` 仅日志；`loop.py:398-495` 的 `empty_retries` / `text_only_retries` / DSML 防御性解析计数器仅本地变量。

### 约束

- **TESTING=1 stub**：`nodes/_llm_utils.py:160-179` 下 `call_llm_streaming` 返回固定 JSON，reasoning / tool_calls 路径不触发；埋点测试需用 `@live` 标记的真实 LLM 用例（nightly 跑）防漂移，stub 路径仅断言"降级 no-op 不报错"。
- **Prompt 双源**：`prompts/loader.py` Langfuse production label 优先、本地兜底；版本号在本地兜底时应记为 `"local"`，不伪造版本。
- **`open_span` 降级契约**：现有 `trace-observability` spec 的"`open_span` 优雅降级"requirement 约定未配置 Langfuse 时返回 `nullcontext`、异常不中断业务 —— 本 delta 所有新埋点必须复用同一兜底，不得新增"Langfuse 异常导致业务失败"路径。
- **单 worker 部署**：StreamRegistry 进程内结构，埋点不得引入跨进程依赖。

## Goals / Non-Goals

**Goals:**

- generation output 同时含 `answer` + `reasoning` + `tool_calls` 三段，事故复盘可读 LLM 完整决策链。
- generation metadata 含 `prompt_name` + `prompt_version`，prompt 迭代在 trace 可追溯（兑现 ADR-0015）。
- AKShare 取数与降级 / 重试路径在 trace 可见，且失败 / 降级有 `level` 区分（ERROR / WARNING）。

**Non-Goals:**

- **不包 ReAct 每轮独立 span** —— `loop.py:329-622` 的 while 循环每轮建 span 涉及迭代边界协议设计（step 号透传、OTel 父子关系），改动面大，留独立后续 delta。
- **不包 routing 决策结构化标记** —— `routing.py` 的路由分支（`after_validate` FAIL→END 等）无 span，需 LangGraph 事件钩子，属另一议题。
- **不包跨线程 `run_deep_analysis` 父子 span 传播** —— `agent_factory.py:372-386` 的 OTel context 跨 `run_in_executor` 传播不保证，需 contextvars 显式传递，留后续。
- **不改任何业务行为 / 不改校验逻辑** —— 纯观测埋点；校验加固属 `harden-llm-output-validation`，互不重叠。
- **不做 trace 采样 / 体积裁剪策略** —— 大体积 span（DataFrame / 长 reasoning）的裁剪留 Open Question，本 delta 先全量记录。

## Decisions

### 决策 1：reasoning / tool_calls 写入 generation output 的结构

**选择**：generation output 用结构化对象而非拼接字符串：
```python
obs.update(output={
    "answer": _accumulated_text,
    "reasoning": _accumulated_reasoning,   # 可为空
    "tool_calls": [{"name": tc.name, "arguments": tc.arguments} for tc in parsed_tool_calls],
})
```
**理由**：结构化字段在 Langfuse UI 可分开展示、可被 Judge evaluator 精确读取（`agent-evaluation-suite` 的 `decision_grounding` 需读 trade_decision、`debate_quality` 需读辩论记录）；拼接字符串会丢失结构、污染 answer 文本。
**备选**：拼成 `"reasoning: ...\nanswer: ..."` 文本 —— 否决，破坏现有 answer 字段契约，且 Judge 难解析。

### 决策 2：prompt 元数据透传链路

**选择**：`prompts/loader.py` 的 `load_prompt` 返回 `(template, prompt_name, prompt_version)` 三元组（现仅返回 template）；各节点调用 LLM 时把 `prompt_name` / `prompt_version` 经 `call_llm_streaming(..., prompt_name=..., prompt_version=...)` 透传到 `start_as_current_observation` 的 metadata。本地兜底时 `prompt_version="local"`、`prompt_name` 仍取文件名。
**理由**：版本号源头唯一（loader），避免各节点重复推断；`@lru_cache` 已缓存 loader，无额外 IO。
**备选**：在 `llm.py` 内部从调用栈反推 prompt 名 —— 否决，脆弱且本地兜底时拿不到 Langfuse 版本号。

### 决策 3：数据源 span 命名与粒度

**选择**：`open_span(name=f"data_source:{source}", input={"symbol": ..., "fields": [...]})`，`source` 取 `akshare` / `tavily` / `internal`。AKShare 内部每类报表（balance_sheet / income / cashflow / kline / news ...）各自一个子 span，而非把 `fetch_data` 整个包成一个 span。
**理由**：incident 008 复盘需要定位"哪个子调用卡住"；整包 span 无法区分。粒度对齐 `fetch.py` 现有的 `ak.fetch_xxx()` 调用边界。
**备选**：只包 `fetch_data` 一个大 span —— 否决，达不到定位子调用的目的（这正是 incident 008 的盲区）。

### 决策 4：降级 / 重试 span 的承载方式

**选择**：不新建独立 span，而是 `update_current_span(metadata={...})` 写到当前所在节点 span（analysts span / react_loop span / tool span）。metadata 字段：`{"degradation": "parse_degraded", "raw_excerpt": "...", "count": N}`。失败 / 降级用 `level`：数据源失败 = `ERROR`，解析降级 / 重试 = `WARNING`。
**理由**：这些事件是节点内部子状态，独立 span 会污染 span 树且无独立耗时意义；metadata + level 既可见又不破坏拓扑。`update_current_span` 复用现有 helper（已带降级兜底）。
**备选**：每条降级建独立 `event` span —— 否决，数量不可控（空输出重试可能 N 次），膨胀 trace。

### 决策 5：大体积内容裁剪边界

**选择**：`reasoning` 与 `tool_calls.arguments` 单字段超 8KB 时截断保留首尾 + 中部省略标记；AKShare 返回的 DataFrame 不入 span output（只记 `{"rows": N, "columns": [...]}` 摘要）。
**理由**：Langfuse span 有体积上限，AKShare 三大报表动辄数十列数百行，全量入 span 会撑爆并拖慢 UI；reasoning 过长同理。摘要足以定位，原始数据可在 state / 日志查。
**备选**：全量记录 —— 否决，实测三大报表序列化会触发 Langfuse 字段超限。

## Risks / Trade-offs

- **[埋点异常影响业务]** → 全部新埋点经 `open_span` / `update_current_span` 包裹，复用现有降级契约（未配置 / 异常 = no-op），且测试覆盖"Langfuse 抛异常时业务仍正常完成"。
- **[reasoning 体积膨胀 trace 成本]** → 决策 5 的 8KB 裁剪；Judge 评估只读结构化字段不依赖全文。
- **[tool_calls 写入与现有 answer 契约不兼容]** → output 从字符串升级为对象，`@live` 测试与 citation_node 读 state 不受影响（它们读 state 不读 generation output）；仅 Langfuse UI 展示变化。
- **[prompt_version 本地兜底为 "local" 干扰统计]** → metadata 明确标记，Langfuse 过滤时可排除 `local`；可接受。
- **[AKShare 子 span 数量多拖慢 trace]** → 失败快速结束、成功仅摘要；单次 deep 分析约 20-30 个 data_source span，可控。

## Open Questions

- ReAct 每轮独立 span 的迭代号协议（step 号如何透传到 LangGraph callback）—— 留后续 delta，本 delta Non-Goal。
- reasoning 是否需要单独的 observation 类型而非塞进 generation output —— 取决于 Langfuse 4.x 对 generation output 结构化字段的支持度，实施时验证。
