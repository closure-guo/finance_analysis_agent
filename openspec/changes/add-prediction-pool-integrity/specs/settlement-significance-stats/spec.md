# Delta for settlement-significance-stats

## ADDED Requirements

### Requirement: IC/ICIR 信号方向一致性序列

系统 SHALL 按结算期（自然月）计算信号方向一致性序列：**IC(期) = 当期判定完成的日主 long/short 观点中 resolved_win 占可判定（resolved_win + resolved_loss）的比例**（resolved_neutral 与 unresolvable 不进分子分母；duplicate_of_day 永不进入）；回避类（avoidance）结果单独成列、SHALL NOT 混入 IC。**ICIR = mean(IC) / std(IC)**，序列期数 < 6 时 SHALL NOT 展示 ICIR（仅展示各期 IC 与样本数）；ICIR 展示 SHALL 附序列期数与逐期 IC。IC 序列每期样本（当期可判定日主观点数）< 10 时该期 IC SHALL 标注「样本不足」且 SHALL NOT 进入 ICIR 序列。公式与阈值 SHALL 以预登记版本为准（见「口径预登记纪律」）。

#### Scenario: 月度 IC 计算

- **GIVEN** 某月判定完成 12 条日主 long/short 观点（7 win / 3 loss / 2 neutral）
- **WHEN** 计算 IC
- **THEN** IC SHALL 为 7/10 = 0.7，neutral 不进分母
- **AND** 同月若有 30 条 duplicate_of_day 关闭行，IC 不受影响

#### Scenario: 期数不足不展示 ICIR

- **GIVEN** IC 序列仅 4 期
- **WHEN** 请求显著性统计
- **THEN** ICIR SHALL NOT 展示
- **AND** 各期 IC 与样本数 SHALL 照常返回

#### Scenario: 单期样本不足剔除

- **GIVEN** 某月可判定日主观点仅 6 条
- **WHEN** 构建 ICIR 序列
- **THEN** 该期 SHALL 标注「样本不足」并被剔除出 ICIR 序列

### Requirement: 敞口对齐蒙特卡洛零模型

对任何对外报告的组合区间读数（区间超额收益），系统 SHALL 产出敞口对齐的蒙特卡洛零模型定位：随机化对象为**同 universe 内随机替换选股**——保持每个决策归属日每个方向（long/short/neutral）的注数与真实组合完全一致（敞口对齐），标的从该归属日 universe（cohort 池或同口径股票池）中均匀随机抽取，抽取 SHALL NOT 使用结算时点之后的信息（无前视）；抽样 10,000 次（配置项），报告真实组合区间超额收益在零模型分布中的右尾分位数与 p 值。**「跑赢/跑输」类结论 SHALL 必须附带零模型分位读数，单独出现的点估计 SHALL 视为口径违规**。日主可判定样本 < 10 时零模型 SHALL NOT 产出（沿 §1.9 红线）。零模型计算 SHALL 为纯函数（同输入同输出），随机源以种子显式注入供复现。

#### Scenario: 敞口对齐

- **GIVEN** 真实组合某归属日为 2 long / 5 short / 50 neutral
- **WHEN** 零模型抽样该日随机组合
- **THEN** 随机组合 SHALL 精确保持 2 long / 5 short / 50 neutral 的注数结构
- **AND** 抽取标的 SHALL 来自同 universe、不使用结算后信息

#### Scenario: 结论必须附分位

- **WHEN** 结算报告陈述「组合区间跑赢基准」
- **THEN** 报告 SHALL 同时给出零模型右尾分位与 p 值
- **AND** 未附分位的点估计陈述 SHALL 被口径检查拒绝

#### Scenario: 样本不足不产出

- **GIVEN** 日主可判定样本 8 条
- **WHEN** 请求零模型读数
- **THEN** SHALL 返回不产出说明（沿 settled<10 红线），SHALL NOT 返回分位数

### Requirement: 口径预登记纪律

IC/ICIR 与蒙特卡洛零模型的公式、阈值（±2% 中性带 / 10 样本红线 / 6 期门槛 / 10,000 次抽样）、样本口径（日主观点）SHALL 在**首批 T+20 结算读数产出之前**写入 `docs/evals/metrics.md` §1.9 并以版本号冻结（预登记）。结算与显著性报告 SHALL 引用其消费的预登记版本号；口径变更 SHALL 以新版本登记、披露变更原因，且 SHALL NOT 追溯改写已发布读数的计算方式（历史读数按其产出时版本解释）。

#### Scenario: 预登记先于首批读数

- **GIVEN** 首批 T+20 结算尚未发生
- **WHEN** 本变更实施
- **THEN** metrics.md §1.9 SHALL 已含 IC/ICIR 与零模型口径的预登记版本
- **AND** 首批结算报告 SHALL 引用该版本号

#### Scenario: 口径变更不追改历史

- **GIVEN** 某结算报告已按预登记 v1 产出读数
- **WHEN** 口径变更为 v2
- **THEN** 新读数按 v2 计算
- **AND** 已发布读数 SHALL 保持 v1 解释，SHALL NOT 被追改
