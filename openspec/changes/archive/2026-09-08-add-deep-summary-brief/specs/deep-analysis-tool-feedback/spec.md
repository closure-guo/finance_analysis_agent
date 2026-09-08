# Delta Spec: deep-analysis-tool-feedback

## ADDED Requirements

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