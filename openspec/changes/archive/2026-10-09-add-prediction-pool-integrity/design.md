# Design: add-prediction-pool-integrity

## Approach

**不动落库层，在判定/统计消费层建「日主观点」视图。**三个组件：

1. **归属日派生复用**：`settle_entry_price` 的派生规则（收盘前→当日；收盘后/非交易日→次一交易日）已存在于结算链路，提取为共享纯函数 `derive_attribution_date(created_at)`。归属日的日终封闭性（收盘后产出归次日）保证盘后批次时点当日观点集合已定，日主判定无竞态。

2. **日主视图 + 判定改造**（`track_record/judgment.py` + `job.py`）：判定任务先按 (symbol, 归属日) 分组取 `created_at` 最晚者为日主；同组其余 open 观点中，已被 superseded 结算的保持终态，其余关闭为 `duplicate_of_day`（新 resolution_rule 值，无读数、不上报 Score、不计样本量）。superseded 判定先行于日主关闭（同日观点变更链保留读数）。NAV 盯市（`metrics.py` 组合构成）消费同一视图函数。

3. **显著性统计纯函数**（新模块 `track_record/significance.py`）：IC 月度序列、ICIR、敞口对齐蒙特卡洛零模型（种子注入、同 universe 随机替换、每归属日每方向注数对齐）。产出走结算报告/只读统计端点，前端展示不在本变更范围（仅 duplicate_of_day 徽标属前端改动）。

**存量处理**：不做数据迁移——存量 76 条 open 在下一个判定日批按新规则自然分类；实施时先 dry-run 打印分类结果人工核对（688072 应 1 主 + N duplicate + 既有 superseded 终态不变）。

## Alternatives Considered

- **ingest 时同日 upsert（新观点替换当日旧行）**：违反 track-record 既有 append-only + 快照冻结 requirement，丢失审计链与「全量记录、拒绝幸存者偏差」语义；且「当日最晚」在日中不封闭，主键不稳定。不选。
- **流量打标隔离（rerun/verification 不入池）**：非池股票的手动分析是合法观点（产品语义「任意股票任意时间」），排除会把战绩页退化为 cohort 专属；且来源推断（session 来源/时间特征）误标风险高。不选；重跑流量经日主去重后已无害。
- **仅计算层视图、不落 duplicate_of_day 状态**：open 池持续膨胀（每日 +5~11 条重复），11 月结算报表与 UI 的 open/resolved 计数口径混乱，且重复行永不关闭语义不完整。不选。

## Risks

- **与 superseded 的交互顺序**：必须先处理跨日/同日的 superseded（观点变更有读数），再关闭剩余同日重复——顺序错误会把真实观点变更误标为 duplicate。对策：判定循环显式两阶段 + 回归测试覆盖「同日 short→long 变更链」场景。
- **口径切点**：「全观点→日主」分母切换沿 track-record-versioning 分段不混算登记，切点前读数（现全为样本积累期，无对外胜率读数）不受影响——恰是切点最佳时机（10-08 净值重启前）。
- **时间压力**：10-08 前部署是软窗口（净值重启）+ 11 月初首批结算是硬窗口；metrics.md §1.9 预登记必须先行（AGENTS.md 评估约束：口径先改台账再动代码），若实施延期，预登记部分可独立先行合并。
- **ICIR 分辨率预期管理**：月度 IC 序列到 2027-04 才满 6 期，ICIR 长期不可展示——这是设计属性（诚实门槛）而非缺陷，报告以逐期 IC + 样本数为主读数。
