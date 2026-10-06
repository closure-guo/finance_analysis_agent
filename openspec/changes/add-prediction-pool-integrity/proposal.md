# Proposal: add-prediction-pool-integrity

## Why

生产库观点池被重跑流量污染：76 条 open 观点仅覆盖 13 只股票（688072 一股 18 条，其中 10-02 调试日一天 7 条），同股同日多注使 NAV 权重成为「重跑次数的函数」、违反 11 月首批 T+20 结算要用的 IC/ICIR 独立性假设、并使敞口对齐蒙特卡洛零模型失去意义（incident 032 战绩指标失真同族）。修复窗口硬性：正式净值自 10-08 重新积累、首批完整结算约 11 月初——统计口径必须在首批读数产出**之前**预登记，否则只能事后补口径（自证收益的后门）。

## What Changes

- 定义「**日主观点**」：同一 (symbol, 决策归属日) 的多条观点中 created_at 最晚者为主，其余为同日重复观点；「决策归属日」复用既有 settle_entry_price 派生规则（收盘前产出→当日；收盘后/非交易日→次一交易日），天然日终封闭
- **判定层**：同日重复观点不独立判定、不产独立结算读数——随日批判定关闭为 `duplicate_of_day`（已被 superseded 规则结算的除外，观点变更链保留读数）；落库层保持 append-only 全量记录不变（审计与「拒绝幸存者偏差」语义不动）
- **组合净值**：等权分母从「全观点」改为「日主观点池」（同股同日一注）
- **统计口径**：胜率/平均超额/回避正确率/样本量分母全部切换为日主观点
- **预登记新统计**（首批结算前冻结进 `docs/evals/metrics.md` §1.9）：IC/ICIR 信号方向一致性序列（按结算期聚合，期数 <6 不展示）+ 敞口对齐蒙特卡洛零模型（同池随机替换选股，匹配每期各方向注数，10,000 次抽样，报告真实组合超额的分布分位与 p 值）
- 前端观点日志对 `duplicate_of_day` 行显式徽标（口径变更的用户可见面）

## Capabilities

### New Capabilities
- `settlement-significance-stats`: 结算显著性与信号一致性统计——IC/ICIR 序列、敞口对齐蒙特卡洛零模型、预登记纪律（口径先于首批读数冻结、结算报告引用预登记版本）

### Modified Capabilities
- `track-record`: 判定规则新增「日主观点与同日重复关闭（duplicate_of_day）」；基础统计的分母从全观点切换为日主观点
- `track-record-metrics`: 组合净值曲线的等权分母改为日主观点池

## Impact

- 后端 `src/finance_agent/outcome/track_record/`：judgment.py（日主判定 + duplicate_of_day）、job.py（日批判定循环）、marking.py/ingest.py（归属日派生复用）、metrics.py（组合构成 + IC/蒙特卡洛计算）
- `docs/evals/metrics.md` §1.9：口径预登记（先行任务，先于代码）
- 前端观点日志：重复行徽标（track-record E2E 套件加用例）
- 存量生产库：76 条 open 需在下一个判定日批按新规则自然分类（dry-run 核对，不做数据迁移）
- 时间约束：10-08 前实施部署；11 月首批 T+20 结算消费全部口径
