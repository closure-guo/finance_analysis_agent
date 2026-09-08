# citation-retry-policy Delta

## ADDED Requirements

### Requirement: value_mismatch 单点修复前置分支

value_mismatch 触发定向重试前，系统 SHALL 先评估单点修复适用性：同一分析师同一轮的 value_mismatch FAIL 数 < 3 时，SHALL 采用单点修复——将每处出错句（含所在章节局部上下文，窗口 SHALL 不少于出错句前后各一段）、对应 ground_truth 与申报格式示例，交一次轻量 LLM 调用做叙事一致性改写，改写结果回填正文 markdown。value_mismatch FAIL 数 ≥ 3 或修复调用失败时，SHALL 回退现有目标分析师全量定向重试路径（不重试单点修复失败处）。单点修复 SHALL NOT 改变重试轮数上限 3、停滞降级（本轮失败率 ≥ 上轮 × 80% 提前放行）与轻微失败直判放行的既有语义；单点修复轮次与全量重试轮次共享 iteration_count 计数。

#### Scenario: 稀疏失败走单点修复

- **WHEN** 某分析师本轮 1 条 claim 判 value_mismatch（如 1/46）
- **THEN** 系统 SHALL 发起单点改写（1 次 LLM 调用）而非重跑该分析师全量报告

#### Scenario: 密集失败回退全量重试

- **WHEN** 同一分析师同一轮 4 条 claim 判 value_mismatch
- **THEN** 系统 SHALL 不做单点修复，直接走现有目标分析师定向重试

#### Scenario: 单点修复不改变止损语义

- **WHEN** 连续两轮失败率 35% → 31%（≥ 35% × 80%）
- **THEN** 即使本轮适用单点修复，系统 SHALL 仍按停滞降级提前放行渲染

### Requirement: 修复调用预算记账

每次单点修复 LLM 调用 SHALL 计入管线 LLM 预算记账（与分析师/辩论调用同口径），并 SHALL 在 trace 观测中记录调用模型、输入输出 token 与修复目标 claim 标识。

#### Scenario: 修复调用进预算

- **WHEN** 一轮校验触发 2 处单点修复
- **THEN** 该 2 次 LLM 调用 SHALL 出现在预算记账与 trace usage 中
