# Delta for track-record

## MODIFIED Requirements

### Requirement: 判定规则（Outcome Resolution）

系统 SHALL 按统一规则判定观点：**默认判定窗口 T+20 交易日**（配置项 `OUTCOME_DEFAULT_HORIZON_DAYS`；观点自带 `horizon_days` 则以自带为准，上限 1 年）；**判定入场基准 SHALL 为 `settle_entry_price`（判定时从行情派生，非参考价）**；对同一标的发出方向相反或目标价不同的新观点时，旧的 long/short 观点 SHALL 立即以当前价结算（superseded，入场基准同为派生 `settle_entry_price`）；**neutral 观点 SHALL NOT 走 superseded 提前结算**（回避判定以完整 horizon 窗口为准）。方向判定：long 观点区间超额收益 > +2% → resolved_win；< −2% → resolved_loss；±2% 区间内 → resolved_neutral（计入总数但不计入胜率分子分母）；short 对称。**中性方向（neutral）观点 SHALL 按回避语义判定**：horizon 到点按 long 口径计算区间超额收益，超额 < −2% → avoidance_win（回避下跌正确）、> +2% → avoidance_loss（错过上行）、±2% 内 → avoidance_neutral；结果写 `avoidance_status`，SHALL NOT 写 resolved_* 状态、SHALL NOT 进入胜率。中性带 ±2% 为全局配置项（回避判定共用）。superseded 提前结算 SHALL 同样适用该 ±2% 中性带（与 horizon 到点判定同一带）。停牌/退市/长期无行情 SHALL 标记 unresolvable，计入样本量，不计入胜率，UI 单独标识。**判定链路 SHALL 对 long/short 观点向 Langfuse 上报 decision_hit / decision_return / decision_excess（沿既有规范），neutral 观点 SHALL NOT 上报决议类 Score。**

**日主观点与同日重复关闭**：每条观点 SHALL 派生「决策归属日」（决策产出时间在当日收盘前 → 当日；收盘后或非交易日 → 次一交易日；与 `settle_entry_price` 派生规则同源）。同一 (symbol, 决策归属日) 的多条观点中 `created_at` 最晚者 SHALL 为**日主观点**，其余为**同日重复观点**。同日重复观点中已被 superseded 规则结算的 SHALL 保持其终态（观点变更链保留读数）；其余同日重复观点 SHALL 在日批判定中关闭为终态 `duplicate_of_day`——SHALL NOT 进行方向/回避判定、SHALL NOT 产任何结算读数（resolution_rule 记录为 duplicate_of_day）、SHALL NOT 进入任何统计分母与样本量。日主观点的 T+20 时钟与其 created_at 不受同日重复观点影响。落库层 SHALL 保持 append-only 全量记录（审计与全量留痕语义不变），日主判定为判定/统计消费层的视图行为。

(Previously: 无日主观点概念；同股同日多条观点各自独立判定并全部进入统计——重跑流量使 NAV 权重与统计样本成为重跑次数的函数。)

#### Scenario: 到期判定

- **GIVEN** 某 long 观点到达 horizon 终点（默认第 20 个交易日）
- **WHEN** 判定任务结算
- **THEN** 按区间超额收益判定 resolved_win / resolved_loss / resolved_neutral

#### Scenario: 中性带判定

- **GIVEN** 某 long 观点区间超额收益为 +1.5%（在中性带 ±2% 内）
- **WHEN** 判定
- **THEN** 该观点 SHALL 为 resolved_neutral
- **AND** 计入总数但不计入胜率分子分母

#### Scenario: 中性观点回避判定

- **GIVEN** 某 neutral 观点（watch 映射）到达 horizon 终点，按 long 口径区间超额为 −5%（标的跑输基准超 2%）
- **WHEN** 判定任务结算
- **THEN** avoidance_status SHALL 为 avoidance_win（回避正确）
- **AND** 该观点 SHALL NOT 获得 resolved_* 状态，SHALL NOT 进入胜率分子分母

#### Scenario: 回避错过上行

- **GIVEN** 某 neutral 观点到达 horizon 终点，按 long 口径区间超额为 +6%
- **WHEN** 判定任务结算
- **THEN** avoidance_status SHALL 为 avoidance_loss（错过上行）

#### Scenario: 提前结算（观点变更）

- **WHEN** 对同一标的发出方向相反或目标价不同的新观点
- **THEN** 旧观点 SHALL 立即以当前价格结算判定
- **AND** resolution_rule SHALL 记录为 superseded

#### Scenario: 不可判定

- **GIVEN** 标的停牌 / 退市 / 长期无行情
- **WHEN** 判定任务结算
- **THEN** 该观点 SHALL 标记 unresolvable，计入样本量、不计入胜率

#### Scenario: 同日重跑仅日主观点判定

- **GIVEN** 某标的同一交易日产出 7 条观点（重跑流量，同向 neutral）
- **WHEN** 日批判定运行
- **THEN** created_at 最晚 1 条 SHALL 作为日主观点正常进入判定管线
- **AND** 其余 6 条 SHALL 关闭为 duplicate_of_day，不产结算读数、不计样本量

#### Scenario: 同日观点变更链保留读数

- **GIVEN** 某标的同日先产出 short 观点 A，后产出方向相反 long 观点 B
- **WHEN** B 落库
- **THEN** A SHALL 被 superseded 规则立即结算（读数保留）
- **AND** B SHALL 为当日日主观点，后续同向重跑按同日重复关闭

#### Scenario: 收盘后产出归属次日

- **GIVEN** 某标的当日 15:00 已有日主观点，当日 20:00（收盘后）再次分析产出新观点
- **WHEN** 归属日派生
- **THEN** 新观点归属日 SHALL 为次一交易日，SHALL NOT 夺取当日日主地位
- **AND** 两观点各自作为其归属日的日主观点独立判定

### Requirement: 基础统计（胜率 + 平均超额 + 显著性门槛）

系统 SHALL 计算并返回胜率与平均超额收益。胜率 = resolved_win / (resolved_win + resolved_loss)，neutral 与 unresolvable 不进分母；**胜率与平均超额 SHALL 仅统计 long/short 方向观点**。neutral 观点的回避判定结果 SHALL 单独统计为**回避正确率** = avoidance_win / (avoidance_win + avoidance_loss)（avoidance_neutral 与 unresolvable 不进分母），作为独立辅助指标以单独字段返回，SHALL NOT 混入胜率；回避正确率展示门槛与胜率一致（样本 <10 不展示）。显著性门槛 SHALL 约束展示：样本量 < 10 不展示胜率与评级（仅展示样本数与「样本积累中」）；样本量 10–29 展示胜率并标注「样本较少」；样本量 ≥ 30 完整展示。**上述胜率/平均超额/回避正确率/样本量的分母 SHALL 仅计日主观点：duplicate_of_day 关闭行 SHALL NOT 计入任何分母与样本量（总数与 UI 列表展示不受限）。**「全观点 → 日主观点」分母切换与「默认判定窗口 252→20」SHALL 均按 `track-record-versioning`「战绩分段不混算」机制登记口径切点，切点前后已结算行 SHALL NOT 混入同一读数。评级（0–5 星）属后续增量（阶段 A 不做）。
(Previously: 分母为全观点（含同股同日重复行）；无日主观点口径切点；无默认窗口口径切点分段约束。)

#### Scenario: 胜率口径

- **GIVEN** 10 条日主观点（4 win / 4 loss / 2 neutral）
- **WHEN** 计算胜率
- **THEN** win_rate SHALL 为 0.5

#### Scenario: 重复行不计入分母

- **GIVEN** 同一标的同日 7 条 neutral 观点（1 日主 + 6 duplicate_of_day）全部判定完成
- **WHEN** 计算统计
- **THEN** 回避正确率样本量 SHALL 仅计 1（日主观点）
- **AND** 6 条 duplicate_of_day SHALL 不出现在任何统计分母与样本量中

#### Scenario: 回避正确率独立统计

- **GIVEN** 12 条 neutral 日主观点（6 avoidance_win / 3 avoidance_loss / 3 avoidance_neutral）
- **WHEN** 计算统计
- **THEN** 回避正确率 SHALL 为 6/9 ≈ 0.667，以独立字段返回
- **AND** win_rate SHALL NOT 包含任何 neutral 观点的判定结果

#### Scenario: 回避样本不足不展示

- **GIVEN** 已判定 neutral 日主观点（avoidance_win + avoidance_loss）< 10
- **WHEN** 请求统计
- **THEN** 回避正确率 SHALL 返回 null 与「样本积累中」标注

#### Scenario: 样本量门槛

- **GIVEN** 某 Agent 已判定日主观点数为 9
- **WHEN** 请求总览
- **THEN** 响应 SHALL 不返回胜率与评级
- **AND** SHALL 返回样本数与「样本积累中」标注

#### Scenario: 分母口径切点登记

- **WHEN** 「全观点 → 日主观点」分母切换实施
- **THEN** SHALL 按 track-record-versioning 机制登记切点
- **AND** 切点前按全观点口径结算的读数 SHALL NOT 与切点后日主口径读数混算

#### Scenario: 口径切点分段

- **GIVEN** 库内同时存在 252 窗口与 20 窗口结算的观点
- **WHEN** 计算对外展示的胜率
- **THEN** SHALL 按 `track-record-versioning` 分段机制区分口径，SHALL NOT 混算单一读数

#### Scenario: 空库

- **GIVEN** 无观点记录
- **WHEN** 请求统计
- **THEN** SHALL 返回空统计与「样本积累中」标注，SHALL NOT 伪造读数

