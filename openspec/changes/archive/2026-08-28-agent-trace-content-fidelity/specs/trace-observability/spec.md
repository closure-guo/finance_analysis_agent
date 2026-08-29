## ADDED Requirements

### Requirement: LLM Generation 推理内容可观测

当 LLM 供应商返回独立推理内容（如 DeepSeek 的 `reasoning_content`）时，系统 SHALL 在 Langfuse generation 的 output 中以独立字段记录完整推理文本，与 answer 文本并列，使事故复盘可读 LLM 完整思考链。该埋点 SHALL 经 `open_span` / `start_as_current_observation` 的优雅降级路径，未配置 Langfuse 或序列化异常时不影响业务。引用 ADR-0015。

#### Scenario: 流式 reasoning 写入 generation output

- **WHEN** DeepSeek thinking 模式开启，流式返回 `reasoning_content` delta
- **THEN** 系统 SHALL 在 generation output 累加完整 `reasoning` 字段
- **AND** 该字段与 `answer` 字段并列（结构化对象，非文本拼接）

#### Scenario: 无 reasoning 时不污染 output

- **WHEN** LLM 未返回 `reasoning_content`（非 thinking 模式或供应商不提供）
- **THEN** generation output 的 `reasoning` 字段 SHALL 为空字符串或空值
- **AND** answer 字段保持原行为不变

#### Scenario: reasoning 体积超限裁剪

- **WHEN** 累加的 `reasoning` 单字段超过 8KB
- **THEN** 系统 SHALL 截断保留首尾 + 中部省略标记后写入
- **AND** 不抛序列化异常

#### Scenario: Langfuse 异常不阻断业务

- **GIVEN** 未配置 Langfuse 或 Langfuse 客户端抛异常
- **WHEN** LLM 调用完成
- **THEN** 业务流程 SHALL 正常返回 answer，reasoning 落 trace 的失败仅记日志

### Requirement: LLM Generation 工具调用决策可观测

当 LLM 返回工具调用决策（`tool_calls`）时，系统 SHALL 在 generation output 中记录工具名与参数列表（结构化），而非仅记 answer 文本，使 trace 能回答"LLM 决定调用什么工具"。该埋点 SHALL 经优雅降级路径。

#### Scenario: tool_calls 写入 generation output

- **WHEN** LLM 返回非空 `tool_calls`（含工具名 + arguments）
- **THEN** generation output SHALL 含 `tool_calls` 字段，值为 `[{"name": ..., "arguments": ...}, ...]`
- **AND** arguments 超过 8KB 时按裁剪策略截断

#### Scenario: 无 tool_calls 时 output 不含该字段

- **WHEN** LLM 返回纯文本 answer，无 `tool_calls`
- **THEN** generation output SHALL 不含 `tool_calls` 字段或其值为空列表

#### Scenario: 降级路径同样记录

- **WHEN** `call_llm_with_tools`（`llm.py:301-366`）的 Langfuse 异常降级分支触发
- **THEN** 该分支 SHALL 仍尝试经 `open_span` 记录 tool_calls（若降级到 no-op 则不报错）

### Requirement: LLM Generation Prompt 元数据可追溯

每次 LLM generation SHALL 在 metadata 中记录 `prompt_name` 与 `prompt_version`，兑现 ADR-0015 第 24 行承诺。版本来源为 `prompts/loader.py` 的 Langfuse production label；本地兜底时 `prompt_version` SHALL 标记为 `"local"`。

#### Scenario: Langfuse production label 版本挂载

- **GIVEN** `prompts/loader.py` 成功从 Langfuse 取得 production label 模板（含版本号）
- **WHEN** 节点调用 LLM 经 `call_llm_streaming(prompt_name=..., prompt_version=...)`
- **THEN** generation metadata SHALL 含 `prompt_name` 与对应语义版本号

#### Scenario: 本地兜底标记 local

- **GIVEN** Langfuse 拉取失败，`load_prompt` 回退本地 `*.md`
- **WHEN** 节点调用 LLM
- **THEN** generation metadata 的 `prompt_version` SHALL 为 `"local"`
- **AND** `prompt_name` SHALL 为本地文件名（不含扩展名）

#### Scenario: loader 返回值扩展

- **WHEN** `load_prompt` 被调用
- **THEN** 其返回 SHALL 透传 prompt_name 与 prompt_version（三元组或带版本对象），调用方可取得

### Requirement: 数据源调用 span 可观测

外部数据源调用（AKShare 取数、Tavily 搜索已由现有 search_api_call 覆盖）SHALL 经 `open_span(name=f"data_source:{source}")` 包裹，记录入参与返回摘要；失败 SHALL 标 `level="ERROR"`，使 incident 008 类卡死 / 失败可定位到具体子调用。

#### Scenario: AKShare 取数子 span 覆盖

- **WHEN** `fetch_data` 节点调用 AKShare 的某类接口（balance_sheet / income / cashflow / kline / news 等）
- **THEN** 该调用 SHALL 包在 `data_source:akshare` 子 span 内
- **AND** span input 含 symbol 与请求字段列表

#### Scenario: 取数失败标 ERROR

- **WHEN** 某 AKShare 子调用抛异常或返回空
- **THEN** 该子 span SHALL 标 `level="ERROR"`
- **AND** output 含错误摘要（异常类型 + 消息）

#### Scenario: DataFrame 返回只记摘要

- **WHEN** AKShare 返回 pandas DataFrame
- **THEN** span output SHALL 只记 `{"rows": N, "columns": [...]}` 摘要
- **AND** 不尝试序列化完整 DataFrame

#### Scenario: 降级路径不阻断取数

- **GIVEN** 未配置 Langfuse
- **WHEN** AKShare 取数经 `open_span` 包裹
- **THEN** 取数 SHALL 正常完成（`open_span` 返回 `nullcontext`）

### Requirement: 降级与重试路径 span 可观测

解析降级（`parse_degraded`）、枚举兜底改写（`_sanitize_claims`）、空输出重试、纯文本无工具调用重试、DSML 防御性解析，SHALL 经 `update_current_span(metadata=...)` 写到所在节点 span，含事件类型 / 计数 / 原始片段；降级事件 SHALL 标 `level`（WARNING 或 ERROR），使静默修复在 trace 可见。

#### Scenario: 分析师解析降级可见

- **WHEN** `analysts.py` 的 `_parse_analyst_report` 捕获 JSON 解析异常并产出 `parse_degraded=True` 报告
- **THEN** 所在分析师 span 的 metadata SHALL 记 `{"degradation": "parse_degraded", "raw_excerpt": <截断原文>}`
- **AND** span level SHALL 标 WARNING

#### Scenario: 枚举兜底改写可见

- **WHEN** `_sanitize_claims` 把非法枚举值改写为兜底值
- **THEN** span metadata SHALL 记 `{"degradation": "sanitize_claims", "field": <字段>, "raw": <原值>, "fixed": <兜底值>}`
- **AND** span level SHALL 标 WARNING

#### Scenario: ReAct 重试计数可见

- **WHEN** `loop.py` 触发空输出重试（`empty_retries`）或纯文本无工具调用重试（`text_only_retries`）
- **THEN** `react_loop` span metadata SHALL 记 `{"retries": {"empty": N, "text_only": M}}`
- **AND** 计数大于 0 时 span level SHALL 标 WARNING

#### Scenario: DSML 防御性解析可见

- **WHEN** `loop.py` 检测到 DSML 标记并防御性解析回 tool_calls
- **THEN** `react_loop` span metadata SHALL 记 `{"degradation": "dsml_fallback", "count": N}`
- **AND** span level SHALL 标 WARNING

#### Scenario: 降级路径不阻断业务

- **GIVEN** 未配置 Langfuse 或 `update_current_span` 抛异常
- **WHEN** 节点执行降级路径
- **THEN** 业务 SHALL 正常完成降级处理，仅日志记录埋点失败
