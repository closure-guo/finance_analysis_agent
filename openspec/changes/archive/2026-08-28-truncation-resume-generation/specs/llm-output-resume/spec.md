# llm-output-resume Specification

## ADDED Requirements

### Requirement: 截断时发起断点续写

系统在检测到 `finish_reason=length` 时 SHALL 发起一次续写请求而非重试完整 prompt：续写请求以当前已完成的正文尾部、续写指令与剩余输出预算构造，只生成缺失的尾部；续写成功后与前段正文拼接，返回与未截断时相同结构的结果。Reasoning 不参与续写。

#### Scenario: 首次截断触发续写

- **WHEN** 一次 LLM 生成以 `finish_reason=length` 结束且已有非空正文
- **THEN** 系统以「已生成正文尾部 + 续写指令」构造续写请求，使用剩余输出预算发起第二次生成，并将两次正文拼接为最终输出

#### Scenario: 续写成功返回完整结果

- **WHEN** 续写请求以 `finish_reason=stop`（或 tool_calls）正常结束
- **THEN** 系统返回 `已生成正文 + 续写正文` 的拼接结果，调用方收到与未截断一致的结果结构与 finish_reason

#### Scenario: 截断时正文为空

- **WHEN** 生成以 `finish_reason=length` 结束且正文为空（reasoning 吃光全部配额）
- **THEN** 系统不发起正文续写，按既有 `OutputTruncatedError` 语义处理

### Requirement: 续写请求携带结构进度标注

系统 SHALL 在续写请求中向模型提供当前生成进度：对已生成正文做尽力部分解析，标注已完成字段（✅）、进行中断点字段（⏳）与未开始字段（⬜）；部分解析失败时 SHALL 降级为仅携带正文尾部，不阻断续写。

#### Scenario: JSON 字段中途截断携带进度标注

- **WHEN** 输出为 JSON 结构、截断发生在字段值中途，且已生成正文可部分解析
- **THEN** 续写请求附带进度标注：已闭合顶层字段标 ✅、未闭合字段标 ⏳、其后的字段标 ⬜，标注内容来自已生成文本的解析结果而非模型推测
- **AND** 续写指令仍明确「从断点继续、不要重复已输出内容」

#### Scenario: 部分解析失败降级为仅尾部

- **WHEN** 输出为 JSON 结构但已生成正文无法部分解析（如括号结构被截断不可恢复）
- **THEN** 续写请求省略进度标注，仅携带正文尾部与续写指令继续发起续写，行为与纯尾部基线一致

### Requirement: 续写上限与终止

系统 SHALL 对续写设置上限：续写请求再次 `finish_reason=length` 时停止续写，按既有 `OutputTruncatedError` 语义上抛，不得无限续写。续写总段数 SHALL 记录在观测 metadata 中。

#### Scenario: 续写仍截断则终止

- **WHEN** 续写请求再次以 `finish_reason=length` 结束
- **THEN** 系统停止续写并抛 `OutputTruncatedError`，且观测 metadata 记录 `resume_count=1` 与 `truncated=true`

#### Scenario: 未截断不续写

- **WHEN** 生成以 `finish_reason=stop`（或 tool_calls）正常结束
- **THEN** 系统不发起续写请求，行为与未引入续写时完全一致（零额外调用）

### Requirement: 续写可追溯

系统 SHALL 将续写相关信息写入 generation 观测 metadata：发生续写时记录 `resume_count`；续写仍截断时记录 `truncated=true`。下游（节点层、evals、Langfuse 查询）SHALL 能据此识别输出由续写完成。

#### Scenario: 续写信息落观测

- **WHEN** 一次生成发生了续写
- **THEN** generation 观测的 metadata 含 `resume_count=1`（大于 1 时按实际续写次数），且输出包含拼接的完整正文

#### Scenario: 续写仍截断标记 truncated

- **WHEN** 续写再次截断并上抛 `OutputTruncatedError`
- **THEN** 观测 metadata 同时含 `resume_count` 与 `truncated=true`

### Requirement: 续写拼接契约

续写拼接 SHALL 保证正文不重复、不缺失：续写指令明确要求「从断点继续、不重复已给内容」；拼接输出 = 前段正文（按模型 delta 原样累积）＋ 续写正文（按模型 delta 原样累积）的字符串直接连接。系统 SHALL 在拼接后输出与单段输出相同的数据类型（`complete_text` 返回字符串、`complete_stream`/`complete_stream_async` 事件的 text 片段顺序拼接）。

#### Scenario: 拼接无重复

- **WHEN** 前段正文以「...风险提示」结尾、续写正文以「1. 行业层面...」开头
- **THEN** 拼接结果为「...风险提示1. 行业层面...」（直接连接，不插入分隔符、不裁剪任何一侧）

#### Scenario: 流式事件顺序

- **WHEN** `complete_stream` 触发续写
- **THEN** 事件流按「前段 text 事件 → 续写 text 事件 → finished」顺序发出，收到事件的调用方感知不到截断存在