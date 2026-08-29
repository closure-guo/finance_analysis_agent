# Trace Observability Specification

## Purpose
TBD - created by archiving change trace-observability. Update Purpose after archive.
## Requirements
### Requirement: 工具调用 span 可观测

ReAct Agent 执行工具调用时，系统 SHALL 在 Langfuse trace 中创建名为 `tool:{tool_name}` 的 span（as_type=span），记录工具调用的输入参数与输出结果，使其与 LLM generation span 在 trace 中分层可观测。经 LLM Provider Gateway 调用的 generation，其 trace metadata 额外携带 provider 契约上下文：`profile`、`provider`、`model`、`purpose`、`capability`（tools/json_schema 摘要）、`finish_reason`（归一化后）、`repair_count`、`fallback_from`、`degradation`；业务失败必须带 typed error（如 `OutputContractError` 携带 raw_excerpt），不得只记 "LLM error"。

#### Scenario: 工具执行时创建 span

- **WHEN** ReAct Agent 在 [harness/loop.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/harness/loop.py) 执行任一工具调用（如 web_search、search_stock、run_deep_analysis）
- **THEN** 系统 SHALL 在 Langfuse trace 中创建 `tool:{tool_name}` span，且 span 的 input 字段包含工具调用参数 args

#### Scenario: span 挂载到 react_loop 下

- **WHEN** 工具调用在 react_loop span 上下文内执行
- **THEN** 系统 SHALL 通过 contextvar 自动继承，使 `tool:{tool_name}` span 成为 `react_loop` span 的子 span，与同级的 LLM generation span 在 trace 树中并列

#### Scenario: span 记录 input 和 output

- **WHEN** 工具调用完成
- **THEN** 系统 SHALL 在 `tool:{tool_name}` span 的 input 字段记录工具参数 args，在 output 字段记录工具执行结果 result

#### Scenario: generation 携带 provider 契约上下文

- **WHEN** 任一经 gateway 的 LLM 调用完成（成功或失败）
- **THEN** generation metadata 包含 profile/provider/model/purpose/finish_reason/repair_count/fallback_from/degradation 字段；输出合同触发 repair 时 repair_count ≥ 1

#### Scenario: litellm 运行时防护事件可观测

- **WHEN** adapter 初始化设置 litellm 运行时开关（如 disable_streaming_logging）或泄漏守护测试触发
- **THEN** 防护配置写入 trace metadata（一次性记录），泄漏守护结果记入合同测试报告，不刷屏业务 trace

### Requirement: 网络搜索 span 可观测

系统执行网络搜索时 SHALL 创建名为 `search_api_call` 的 span（as_type=span），记录搜索查询与结果数量，使其在 trace 中与上层调用（工具调用 span 或规则预搜索 span）分层可观测。

#### Scenario: 搜索执行时创建 span

- **WHEN** [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 的搜索函数被调用
- **THEN** 系统 SHALL 创建 `search_api_call` span，input 字段包含 query 与 max_results 参数

#### Scenario: 作为工具调用子 span

- **WHEN** 网络搜索作为 ReAct Agent 的工具调用被执行（上层为 `tool:web_search` span）
- **THEN** 系统 SHALL 通过 contextvar 自动继承，使 `search_api_call` span 成为 `tool:web_search` span 的子 span

#### Scenario: span 记录结果数量

- **WHEN** 网络搜索完成
- **THEN** 系统 SHALL 在 `search_api_call` span 的 output 字段记录返回结果数量 count

### Requirement: open_span helper 优雅降级

系统 SHALL 在 [langfuse_tracing.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/langfuse_tracing.py) 提供 `open_span(name, input)` 上下文管理器，封装 Langfuse span 创建逻辑，并在 Langfuse 未配置时优雅降级，确保 trace 故障不影响业务流程。

#### Scenario: Langfuse 已配置时创建 span

- **WHEN** Langfuse 已配置（`get_langfuse()` 返回有效客户端）且调用 `open_span(name="tool:web_search", input={"args": {...}})`
- **THEN** 系统 SHALL 调用 `start_as_current_observation(name=name, as_type="span", input=input)` 创建 span 并进入其上下文

#### Scenario: Langfuse 未配置时返回 nullcontext

- **WHEN** Langfuse 未配置（`get_langfuse()` 返回 None）且调用 `open_span(...)`
- **THEN** 系统 SHALL 返回 `contextlib.nullcontext()`，不抛出异常、不创建 span、不产生开销

#### Scenario: span 创建异常时降级不影响业务

- **WHEN** `start_as_current_observation` 抛出异常（如 Langfuse 服务不可达）
- **THEN** 系统 SHALL 捕获异常并降级为 nullcontext，确保业务流程继续执行，不因 trace 故障中断工具调用或搜索

### Requirement: span 不改变业务行为

span 的创建 SHALL 对业务行为透明——不改变 SSE 事件流、API 响应内容、工具执行结果，确保 trace 埋点是纯观测层操作。

#### Scenario: span 创建对 SSE 事件流透明

- **WHEN** 工具调用或网络搜索在 span 上下文内执行
- **THEN** 系统 SHALL 发布与无 span 时完全一致的 SSE 事件流（事件类型、顺序、内容不变）

#### Scenario: span 异常时业务结果不变

- **WHEN** span 创建或更新过程中发生异常
- **THEN** 系统 SHALL 仍返回正确的工具执行结果或搜索结果，业务输出不受 trace 故障影响

### Requirement: 评估调用独立环境标记

LLM-as-a-Judge 的调用 trace SHALL 与业务管线 trace 隔离（独立 Langfuse environment 标记），其 generation 记录打分维度、输入变量非空断言结果与分数/失败原因，使评估结果可审计。

#### Scenario: judge 调用带维度与输入审计

- **WHEN** judge 对某维度打分完成
- **THEN** generation metadata 含 dimension、输入变量非空断言结果、score 与 reason；输入缺失时记录 skipped=input_missing 而非正常分数

### Requirement: trace 记录会话内容（根 span output）

系统 SHALL 在管线根 span（`deep_analysis:{股票}`）与 ReAct `react_loop` span 退出前，将 agent 产出写入 span 的 output，使 Langfuse trace/session 层级直接可见 agent 输出，而非仅有 user input。

#### Scenario: deep_analysis 根 span 记录 agent 产出

- **WHEN** 5 层分析管线完成（`deep_analysis:{股票}` 根 span 退出）
- **THEN** 系统 SHALL 将根 span 的 output 更新为管线产出摘要（各 agent 节点产出 + 最终报告摘要）

#### Scenario: react_loop span 记录 agent 最终回复

- **WHEN** ReAct Agent 完成一轮执行（`react_loop` span 退出）
- **THEN** 系统 SHALL 更新 `react_loop` span 的 output 为 agent 最终回复/总结

### Requirement: LLM generation 按子 agent 归因

系统 SHALL 在创建 LLM generation 观测时，以发起该调用的子 agent 名命名 observation（如 `technical_analyst`、`bull_debater`、`risk_judge`、`trader`、`fund_manager`)，使 Langfuse 观测列表可直接区分每次调用归属的子 agent。

#### Scenario: 管线节点 LLM 调用以 agent 名命名

- **WHEN** 管线节点（如 `technical_analyst`）经 `call_llm_streaming(node_name=...)` 触发 LLM 调用，且 Langfuse 已配置
- **THEN** 系统 SHALL 创建 name 为该 agent 名（`technical_analyst`）的 generation observation，而非 `litellm:{model}`

#### Scenario: agent 名透传至 observation

- **WHEN** 任一 LLM 入口（`call_llm` / `call_llm_stream` / `call_llm_with_tools` / harness LLM client）被调用且调用方提供 agent 名
- **THEN** 系统 SHALL 将该 agent 名用作 generation observation 的 name

### Requirement: agent 名缺省时向后兼容

当调用方未提供 agent 名时，系统 SHALL 将 LLM generation observation 命名为 `litellm:{model}`，与本改动前的现状一致，确保未接入 agent 归因的调用点行为不回归。

#### Scenario: 未传 agent 名退化为现状命名

- **WHEN** LLM 入口被调用但未提供 agent 名（或为空字符串）
- **THEN** 系统 SHALL 将该 generation observation 命名为 `litellm:{model}`

### Requirement: generation 携带过滤 metadata

系统 SHALL 在 LLM generation observation 的 metadata 中记录可用的过滤维度字段，包括 `agent`、分析会话 `session_id`、股票 `stock_code`，使 Langfuse 可按 agent 或一次分析运行过滤调用。任一字段在调用上下文不可得时 SHALL 省略该字段而不报错。

#### Scenario: 上下文字段写入 metadata

- **WHEN** 管线节点触发 LLM 调用，且调用上下文提供 session_id / stock_code
- **THEN** 系统 SHALL 在 generation 的 metadata 中记录 `agent`、`session_id`、`stock_code`

#### Scenario: 字段缺失时省略不报错

- **WHEN** 调用上下文中 session_id 或 stock_code 不可得
- **THEN** 系统 SHALL 省略对应 metadata 字段，正常完成观测创建，不抛出异常

### Requirement: 观测改动对业务透明

LLM generation 的命名与 metadata SHALL 为纯观测层操作，不改变 SSE 事件流、API 响应内容、LLM 的输入 prompt 或输出内容；Langfuse 未配置时系统 SHALL 不创建观测、不影响业务流程。

#### Scenario: Langfuse 未配置时零影响

- **WHEN** Langfuse 未配置（`get_langfuse()` 返回 None）
- **THEN** 系统 SHALL 跳过 observation 创建，LLM 调用与业务流程正常执行

#### Scenario: 观测埋点不改变 LLM 内容

- **WHEN** LLM 调用附带 agent 命名 / metadata
- **THEN** 系统 SHALL 发送与无埋点时完全一致的 prompt，且返回内容不变

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
