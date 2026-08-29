## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: 评估调用独立环境标记

LLM-as-a-Judge 的调用 trace SHALL 与业务管线 trace 隔离（独立 Langfuse environment 标记），其 generation 记录打分维度、输入变量非空断言结果与分数/失败原因，使评估结果可审计。

#### Scenario: judge 调用带维度与输入审计

- **WHEN** judge 对某维度打分完成
- **THEN** generation metadata 含 dimension、输入变量非空断言结果、score 与 reason；输入缺失时记录 skipped=input_missing 而非正常分数
