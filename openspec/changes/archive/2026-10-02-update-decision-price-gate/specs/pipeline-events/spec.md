# Delta for pipeline-events

## ADDED Requirements

### Requirement: 管线阻断终态可见化

管线在未产出最终报告的情况下正常结束（图流自然耗尽、无异常抛出）时——无论阻断来源是决策价位交叉校验门禁、勾稽校验 FAIL 还是其他前置门禁——系统 SHALL 将会话 status 更新为 failed 并持久化 `failure_reason`（含可归因的阻断来源描述），MUST NOT 使会话停留于 running 等待超时兜底。失败通知 SHALL 按执行路径走既有通道：fast path（`_run_graph_streaming`）经既有 SSE error 终态事件；ReAct 慢路径（run_deep_analysis 工具）经既有 TOOL_RESULT 通知（带 `pipeline_blocked` 标记，形态同该路径超时/异常先例）。

#### Scenario: 决策价位门禁阻断的会话终态

- **GIVEN** risk_judge 的决策价位交叉校验打回重试后仍存在 anomaly（price-level-tooling 门禁语义）
- **WHEN** 管线路由跳过 fund_manager 与 generate_report 正常结束
- **THEN** 会话 status SHALL 更新为 failed，failure_reason SHALL 含「决策价位交叉校验」阻断描述
- **AND** fast path 的 SSE 流 SHALL 下发 error 类型终态事件；ReAct 慢路径 SHALL 下发带 `pipeline_blocked` 标记的 TOOL_RESULT 通知
- **AND** 会话 MUST NOT 写入报告产物，MUST NOT 落决策结算日志（final_trade_decision 未经审批）

#### Scenario: 勾稽校验 FAIL 的会话终态

- **GIVEN** validate_financials 判定硬等式不通过（validation_result=FAIL）路由至 END
- **WHEN** 管线在未产出报告的情况下正常结束
- **THEN** 会话 status SHALL 更新为 failed，failure_reason SHALL 含勾稽校验阻断描述
- **AND** 会话 MUST NOT 停留于 running 直至管线超时

#### Scenario: 正常完成路径不受影响

- **GIVEN** 管线正常产出最终报告
- **WHEN** 图流结束且报告已下发
- **THEN** 会话 status SHALL 照常更新为 completed，MUST NOT 被误标 failed
