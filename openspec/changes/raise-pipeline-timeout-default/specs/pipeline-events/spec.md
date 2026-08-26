# Delta for Pipeline Events

## MODIFIED Requirements

### Requirement: 管线超时与中断检测

系统 SHALL 对深度分析管线实施全局超时机制：管线启动后超过最大执行时间未完成时，系统 SHALL 将会话标记为 failed 并记录超时原因。会话 status 更新为 failed 时 SHALL 持久化 `failure_reason` 字段，使客户端能展示具体中断原因而非笼统的"可能已中断"。默认最大执行时间从 10 分钟上调为 40 分钟，以匹配 LLM 端点的生成耗时方差（实测单节点 3.7~15.7 分钟，R1+R2 合法双轮最坏约 32 分钟）。
(Previously: 默认最大执行时间 10 分钟)

#### Scenario: 管线全局超时

- GIVEN 某会话的深度分析管线已启动并在后台运行
- WHEN 管线执行时间超过配置的最大执行时间（默认 40 分钟）
- THEN 系统 SHALL 终止管线执行
- AND SHALL 将会话 status 更新为 failed
- AND SHALL 在 failure_reason 中记录"管线执行超时"

#### Scenario: 环境变量覆盖默认

- GIVEN 部署方设置了 PIPELINE_TIMEOUT_SECONDS 环境变量（如 "600"）
- WHEN 管线执行时间超过该环境变量配置的值
- THEN 超时判定 SHALL 以环境变量配置为准（默认值仅作未配置时兜底）

#### Scenario: 管线异常中断原因持久化

- GIVEN 管线执行过程中发生异常（数据拉取失败、LLM 调用失败、节点异常等）
- WHEN 异常导致管线中止
- THEN 系统 SHALL 将会话 status 更新为 failed
- AND SHALL 在 failure_reason 中记录异常类型与摘要信息
- AND 客户端切回该会话时 SHALL 通过 GET /api/sessions/{id} 获取 failure_reason 并展示