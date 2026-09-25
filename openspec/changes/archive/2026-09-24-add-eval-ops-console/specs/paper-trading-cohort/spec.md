# Delta for paper-trading-cohort

## MODIFIED Requirements

### Requirement: 成本预算与运维开关

cohort 跑批 SHALL 由显式运维开关控制，默认关闭；开关关闭时调度器 SHALL NOT 触发任何跑批。开关与跑批时刻的**唯一真相源 SHALL 为持久化运维配置**（`ops_config`），环境变量（`COHORT_ENABLED` / `COHORT_HOUR` / `COHORT_MINUTE`）SHALL 仅作进程启动时的引导默认值；运行期修改（含界面操作）SHALL 即时生效且重启后保持。开关与时刻 SHALL 可在评估运维分区界面操作（开启带确认与成本展示，见 `eval-ops-console`「cohort 开关与时刻的界面控制」）。每轮跑批的 LLM 调用数与 token 成本 SHALL 汇总落记账；单轮成本达到预算上限（配置项）时 SHALL 停止本轮后续标的、记账 skipped 并告警。跑批 SHALL 串行执行且置于可配置的时移窗口（默认盘后），SHALL NOT 与用户流量并发争抢（单 worker / StreamRegistry 约束）。
(Previously: 开关与时刻仅由环境变量控制，修改须重启进程；无界面操作路径，也无持久化配置层。)

#### Scenario: 默认关闭

- **GIVEN** 运维开关未显式开启（持久化配置与环境变量均无开启值）
- **WHEN** 到达配置的跑批时刻
- **THEN** SHALL NOT 触发跑批，SHALL NOT 产生任何 LLM 调用

#### Scenario: 预算超限熔断

- **GIVEN** 本轮已耗 token 达到单轮预算上限
- **WHEN** 处理下一标的前
- **THEN** SHALL 停止本轮，剩余标的记账 skipped（原因=预算熔断）并告警
- **AND** 已启动的分析 SHALL 正常完成落库，不中断丢弃

#### Scenario: 成本随轮落账

- **WHEN** 一轮跑批结束
- **THEN** 记账 SHALL 含本轮逐标的与汇总的 LLM 调用数 / token 成本（usage 真值，非估算）

#### Scenario: 界面开关持久化与即时生效

- **GIVEN** owner 在界面开启开关并把时刻改为 19:30
- **WHEN** 保存成功
- **THEN** 无需重启，下一触发 SHALL 按 19:30 且开关为开
- **AND** 进程重启后 SHALL 保持该设定，不回退环境变量

#### Scenario: 关闭空转留痕

- **GIVEN** 开关为关
- **WHEN** 到达跑批时刻
- **THEN** 运行历史 SHALL 记一行 skipped-disabled（零 LLM 调用）
- **AND** SHALL NOT 以「无记录」冒充「未触发」
