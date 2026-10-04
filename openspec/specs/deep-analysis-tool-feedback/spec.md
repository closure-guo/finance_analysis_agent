# deep-analysis-tool-feedback Specification

## Purpose

定义 `run_deep_analysis` 工具完成时返回给 Agent LLM 的内容契约：输出 SHALL 包含管线各层结论的结构化摘要，使 ReAct 摘要 LLM 具备填全 `deep_mode.md` 摘要全部字段所需的上游材料（对齐 `agent-prompt-contracts`「摘要仅基于输入材料」）。防止因误用固定字符截断导致辩论/交易/风控/基金经理章节不可见、摘要字段退化为「本次分析未覆盖」。

## Requirements

### Requirement: run_deep_analysis 工具返回内容含各层结论

`run_deep_analysis` 工具完成后返回给 Agent LLM 的输出（`llm_output`）SHALL 包含结构化结论摘要，覆盖管线的关键结论章节——多空辩论结论、交易决策、风控裁决、基金经理决策、各分析师一句话——使摘要 LLM 具备填全 `deep_mode.md` 摘要全部字段所需的上游材料（对齐 `agent-prompt-contracts`「摘要仅基于输入材料」）。SHALL NOT 以固定字符数截断报告正文作为唯一内容（如 `report_md[:2000]`），因报告前段多为图表列表与分析师章节开头，辩论/交易/风控/基金经理章节位于截断线之后时将导致 LLM 无法提取 → 摘要字段退化为「本次分析未覆盖」。

- 结构化摘要各字段 SHALL 做长度保护（单字段截断），整体不超 harness `tool_result_budget`（50000 字符）上限。
- 报告正文节选 SHOULD 保留在输出尾部供引用，但不得作为唯一内容。

#### Scenario: 深分析完成返回结构化结论

- **WHEN** `run_deep_analysis` 管线正常完成，`accumulated` 含 `research_manager_conclusion`、`trader_plan`、`final_trade_decision`、`fund_manager_decision`、`analyst_reports`
- **THEN** 工具输出 SHALL 包含多空辩论结论文本、交易决策方向与理由、基金经理决策值、及至少一位分析师的一句话结论
- **AND** 输出 SHALL NOT 仅截取 `report_md[:2000]`（即当报告总长 >2000 时，输出中的结论章节 SHALL 可见）

#### Scenario: 某层结论缺失不抛异常

- **WHEN** `accumulated` 缺少某一结论字段（如 `fund_manager_decision` 空）
- **THEN** 工具输出 SHALL 跳过该字段继续拼装，SHALL NOT 抛异常，SHALL NOT 输出占位符

#### Scenario: 摘要字段长度受保护

- **WHEN** 单个结论字段内容超长（如 debate 结论数千字符）
- **THEN** 该字段 SHALL 被截断到受控长度，整体工具输出不失控

### Requirement: 管线异常终止的工具结果显式错误语义

`run_deep_analysis` 在管线异常终止（超时 / 异常 / 事件流中断 / 生成器提前结束）时 SHALL 返回显式错误的 TOOL_RESULT：`is_error=True`、输出文本含可读失败原因、metadata 携带机器可读标志（对齐既有 `pipeline_timeout` / `pipeline_error` / `pipeline_blocked` 约定），MUST NOT 返回空串或不返回 TOOL_RESULT。harness SHALL 将 output 为空的 TOOL_RESULT 视为工具失败（等价于结果缺失），SHALL NOT 置位 `analysis_completed`。ReAct 摘要轮的输入材料 SHALL 包含机器可读的异常标志，使「管线异常终止」与「正常无报告」对摘要 LLM 机器可区分；摘要 LLM MUST NOT 将管线异常终止转述为「本次未返回有效报告内容」等语义等价的歧义文案（incident 037：报告文件完好但用户被告知无报告）。

#### Scenario: 管线超时返回显式错误

- **WHEN** `run_deep_analysis` 管线超时终止
- **THEN** TOOL_RESULT 满足 `is_error=True` 且 metadata 含 `pipeline_timeout=True`
- **AND** 输出含超时的可读原因，不出现空串输出

#### Scenario: 事件流中断不产生空结果歧义

- **GIVEN** 事件队列丢弃或生成器提前结束导致 TOOL_RESULT 缺失或 output 为空
- **WHEN** harness 消费该工具结果
- **THEN** 按工具失败处理（`is_error=True` 语义），`analysis_completed` 不置位
- **AND** 后续摘要轮输入含显式失败标志，摘要可陈述「分析异常终止」而非「无有效报告」

#### Scenario: 阻断终态语义不回退

- **WHEN** 价位校验等门禁阻断交付（既有 `pipeline_blocked` 路径）
- **THEN** 既有语义保持：TOOL_RESULT 携带 `failure_reason`、会话置 failed，不因本需求引入回归

#### Scenario: 正常完成契约不受影响

- **WHEN** 管线正常完成
- **THEN** 既有「run_deep_analysis 工具返回内容含各层结论」需求的原有行为不变
