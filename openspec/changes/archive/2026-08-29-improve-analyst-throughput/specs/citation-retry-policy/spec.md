# Delta for Citation Retry Policy

## ADDED Requirements

### Requirement: 引用校验重试降级

系统 SHALL 对引用校验（citation）失败后的分析师重试实施降级控制：当最新一轮校验失败率不低于上一轮失败率的 80%（无显著改善）时，系统 SHALL 提前终止重试并放行渲染（render），不再派发下一轮分析师。重试总轮数上限 SHALL 保持 3（iteration_count < 3），降级判定 SHALL 不放宽该上限。降级触发 SHALL 在 trace 观测中留下可判读标记。

#### Scenario: 失败率无改善提前放行

- GIVEN 第一轮分析师后引用校验失败率为 35%，触发重试
- WHEN 第二轮分析师后失败率为 31%（≥ 35% × 80%）
- THEN 系统 SHALL 不派发第三轮分析师，直接放行渲染
- AND 降级决策 SHALL 记录到 Langfuse trace（可判读的降级标记）

#### Scenario: 失败率显著改善保留重试

- GIVEN 第一轮分析师后引用校验失败率为 60%，触发重试
- WHEN 第二轮分析师后失败率为 20%（< 60% × 80%）
- THEN 系统 SHALL 按既有上限（iteration_count < 3）继续重试

#### Scenario: 轮数上限不因降级放宽

- GIVEN 任意失败率序列
- WHEN 引用校验连续失败
- THEN 分析师执行总轮数 SHALL NOT 超过 3
