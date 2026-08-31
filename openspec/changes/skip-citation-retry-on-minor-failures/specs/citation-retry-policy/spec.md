# Delta for Citation Retry Policy

## MODIFIED Requirements

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