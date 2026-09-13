# Delta for citation-retry-policy

## MODIFIED Requirements

### Requirement: 引用校验重试降级

自动重试默认停用：`CITATION_AUTO_RETRY_ENABLED = False` 时，引用校验非 PASS 状态 SHALL 直接放行渲染，SHALL NOT 派发分析师重跑轮；fail_buckets / retry_targets / fail_rates 的计算与 trace 观测 SHALL 保留。重试启用时，既有降级控制继续生效：失败率不低于上一轮 80% 提前终止、轮数上限 3 不放宽、轻微失败（FAIL ≤ 1 且失败率 ≤ 5%）直接放行。重试触发 SHALL 仅来自「重试准入桶」（`CITATION_RETRY_ADMITTED_BUCKETS`，当前为空集）——桶进入准入集合的前提是有逐条人工终裁记录确认其为真错误。重试启用且目标分析师在重跑后输出内容不变时，系统 SHALL 立即放行渲染并在 trace 留下可判读标记（不等待失败率停滞判定）。
(Previously: value_mismatch/direction_mismatch 桶与 coverage-gap 自动触发定向重试；incident 026 终裁两桶 100% 误报，r2 九条 deep 分析师生成 75 次、fundamental 25 次，零收益且以降级版覆盖正常报告)

#### Scenario: 停用状态下非 PASS 直接放行

- **WHEN** 引用校验存在 FAIL 或覆盖缺口，且 `CITATION_AUTO_RETRY_ENABLED = False`（默认）
- **THEN** `after_citation` SHALL 返回 `render`，SHALL NOT 派发任何分析师重跑轮

#### Scenario: 停用状态下观测不退化

- **WHEN** 停用状态下的任意一轮校验
- **THEN** fail_buckets / retry_targets / fail_rates / 覆盖缺口 SHALL 照常计算并写入 state 与 trace

#### Scenario: 既有失败率无改善提前放行

- **WHEN** 重试启用且最新一轮失败率 ≥ 上一轮 × 80%
- **THEN** 系统 SHALL 提前终止重试并放行渲染，轮数上限 3 不放宽，trace 留可判读标记

#### Scenario: 既有轻微失败免除重试

- **WHEN** 重试启用且单轮 FAIL 数 ≤ 1 且失败率 ≤ 5%
- **THEN** 系统 SHALL 直接放行渲染并留可判读标记

#### Scenario: 未准入桶不触发重试

- **WHEN** 重试启用且 FAIL 仅落在 `CITATION_RETRY_ADMITTED_BUCKETS` 之外的桶（如 value_mismatch / direction_mismatch / path_unresolvable）
- **THEN** 系统 SHALL 放行渲染；桶 SHALL 照常计入观测指标

#### Scenario: 准入条件

- **WHEN** 拟将某失败桶加入 `CITATION_RETRY_ADMITTED_BUCKETS`
- **THEN** SHALL 先存在该桶逐条人工终裁记录（incidents 或 tests/validation）确认桶内为真错误，方可加入

#### Scenario: 重写无进展立即停

- **WHEN** 重试启用且目标分析师重跑后 markdown 哈希与重跑前一致
- **THEN** 系统 SHALL 立即放行渲染并在 trace 留下可判读标记（`citation_retry_no_progress`），SHALL NOT 等待失败率停滞判定
