# Delta for deep-analysis-tool-feedback

## ADDED Requirements

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
