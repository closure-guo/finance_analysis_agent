# citation-retry-policy Specification

## Purpose
TBD - created by archiving change improve-analyst-throughput. Update Purpose after archive.
## Requirements
### Requirement: 引用校验重试降级

系统 SHALL 对引用校验（citation）失败后的分析师重试实施降级控制：当最新一轮校验失败率不低于上一轮失败率的 80%（无显著改善）时，系统 SHALL 提前终止重试并放行渲染（render），不再派发下一轮分析师。重试总轮数上限 SHALL 保持 3（iteration_count < 3），降级判定 SHALL 不放宽该上限。降级触发 SHALL 在 trace 观测中留下可判读标记。
(Previously: 同前句，未覆盖轻微失败场景)

系统 SHALL 在单轮引用校验失败**轻微**时直接放行渲染，不启动分析师重试轮：**FAIL 数 ≤ 1 且失败率 ≤ 5%**。校验器为确定性纯函数，同 claim 重跑必复现该 FAIL（incident 022 实测：1/46=2.2% FAIL 触发 1–2 轮全量重跑，零收益）；轻微失败直接放行的决策 SHALL 与既有降级一样在 trace 观测中留下可判读标记。
(Previously: 无此条款——任一 FAIL（citation_pass=false）即触发重试，单点失败引发全量重跑空转)

#### Scenario: 失败率无改善提前放行

- GIVEN 第一轮分析师后引用校验失败率为 35%，触发重试
- WHEN 第二轮分析师后失败率为 31%（≥ 35% × 80%）
- THEN 系统 SHALL 不派发第三轮分析师，直接放行渲染

#### Scenario: 失败率显著改善保留重试

- GIVEN 第一轮分析师后引用校验失败率为 60%，触发重试
- WHEN 第二轮分析师后失败率为 20%（< 60% × 80%）
- THEN 系统 SHALL 按既有上限（iteration_count < 3）继续重试

#### Scenario: 轮数上限不因降级放宽

- GIVEN 任意失败率序列
- WHEN 引用校验连续失败
- THEN 分析师执行总轮数 SHALL NOT 超过 3

#### Scenario: 轻微失败免除重试

- GIVEN 第一轮分析师后引用校验结果（如 46 条 claim 中 1 条 FAIL，失败率 2.2%）
- WHEN FAIL 数 ≤ 1 且失败率 ≤ 5%
- THEN 系统 SHALL 直接放行渲染，SHALL NOT 派发第二轮分析师
- AND 该放行决策 SHALL 在 trace 观测中留下可判读标记

#### Scenario: 非轻微失败仍走既有路径

- GIVEN 第一轮分析师后引用校验失败数为 13/24（失败率 54.2%）
- WHEN FAIL 数 > 1 且失败率 > 5%
- THEN 系统 SHALL 按既有规则重试（停滞降级 / 轮数上限约束）

### Requirement: 定向重试反馈携带 direction 申报提示

校验失败触发的定向重试反馈（value_mismatch / direction_mismatch 桶）与 coverage 打回（coverage_gap）SHALL 在反馈条目中携带 direction 申报提示：未申报 direction 的覆盖缺口 SHALL 提示「补登记时同步申报 direction」；direction_mismatch 的重试反馈 SHALL 携带校验器解析的真值符号，分析师 SHALL 据此修正 stated_value 与 direction 的组合而非仅改数值。

#### Scenario: direction_mismatch 重试反馈含真值符号

- **WHEN** claim 因 direction_mismatch 判 FAIL 进入定向重试
- **THEN** 反馈条目 SHALL 包含 ground_truth 数值及其符号，与 direction 申报格式示例

#### Scenario: 覆盖缺口补登记携带 direction 提示

- **WHEN** coverage 打回生成 coverage_gap 反馈条目
- **THEN** 条目 SHALL 包含 direction 申报提示字段，提示分析师补 claim 时一并申报方向

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

