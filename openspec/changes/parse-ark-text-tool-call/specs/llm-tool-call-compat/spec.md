# Delta for LLM Tool Call Compat

## ADDED Requirements

### Requirement: 方舟文本格式工具调用识别

harness 的 ReAct LLM 客户端 SHALL 在流式文本增量中识别方舟 GLM 的文本格式工具调用 `<tool_call>NAME<arg_key>K</arg_key><arg_value>V</arg_value>…</tool_call>`（单个块内多组 arg_key/arg_value，值均为字符串），并将其转换为结构化工具调用下发执行；识别到的块文本 SHALL NOT 作为正文下发。正常正文的下发延迟 SHALL NOT 超过一个标签前缀的长度（不得为检测而整段缓冲）。流结束时仍未闭合的疑似块 SHALL 原样作为正文返回，不得吞掉内容。

#### Scenario: 完整文本块转为结构化调用

- GIVEN LLM 流式输出 `重试一次。<tool_call>run_deep_analysis<arg_key>stock_code</arg_key><arg_value>601700</arg_value></tool_call>` 后结束
- WHEN harness LLM 客户端消费该流
- THEN 前缀正文 `重试一次。` 正常下发
- AND 产出结构化工具调用（name=run_deep_analysis，arguments={"stock_code": "601700"}）
- AND `<tool_call>…</tool_call>` 块文本不进入正文

#### Scenario: 标签跨增量分割仍可识别

- GIVEN 标签 `<tool_call>` 与 `</tool_call>` 被切分在多个流式增量中到达
- WHEN harness LLM 客户端消费该流
- THEN 识别 SHALL 照常完成，不因分割而漏判或把标签片段当正文下发

#### Scenario: 无标签正文不受影响

- GIVEN 流式正文不含任何工具调用标签
- WHEN harness LLM 客户端消费该流
- THEN 正文 SHALL 原样透传，尾部至多保留一个标签前缀长度的待定字符并在流结束时补发

#### Scenario: 未闭合块原样返回

- GIVEN 流中出现 `<tool_call>` 后直至流结束都未出现 `</tool_call>`
- WHEN harness LLM 客户端消费该流
- THEN 未闭合内容（含开标签）SHALL 原样作为正文返回，不得静默丢弃
