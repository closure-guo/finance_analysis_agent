## ADDED Requirements

### Requirement: 上下文预算按 capability 派生

`harness/ContextBudget` 的总上下文预算 SHALL 从当前 `ModelProfile.capability.max_context` 派生，禁止全局固定 `max_context_tokens=120000`。预算拆分为 system reserve、tool schema reserve、history budget、output reserve。usage 真实值存在时用于校准 token 计数；不存在时估算并标记 `usage_estimated=true`。
(Previously: ContextBudget 硬编码 120000，与 profile 无关。)

#### Scenario: 长上下文 profile 获得更大预算
- **WHEN** 当前 profile capability.max_context=200000
- **THEN** ContextBudget 总预算为 200000，各 reserve 按比例派生

#### Scenario: 估算 token 标记
- **WHEN** 本轮无真实 usage 返回
- **THEN** 预算校准基于估算值，trace 记录 usage_estimated=true

### Requirement: 输出预算与观测预算字段

每次 generation 观测 SHALL 携带预算派生信息：`max_tokens` 派生来源（capability.max_output 或显式 requested）与 `usage_estimated` 标记；错误 MUST 携带 `error_type` 分类字段，不允许只记录字符串错误。
(Previously: max_tokens 派生来源未落 trace；错误观测无强制 error_type。)

#### Scenario: 派生来源落 trace
- **WHEN** 调用未显式传 max_tokens 且由 capability.max_output 派生
- **THEN** generation 观测记录派生来源为 capability
