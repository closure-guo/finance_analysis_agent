# Delta for track-record-metrics

## MODIFIED Requirements

### Requirement: 风险收益指标引擎

系统 SHALL 日批重算 `agent_metrics_daily`:样本量/胜率/平均超额/年化收益/波动率/夏普(无风险利率默认 2%,配置化)/最大回撤/风险分 `clip(round(0.6*dd+0.4*vol),1,10)`(映射表配置化)/**组合 β 与年化 Jensen α**。β/α 口径:由 equity 双净值序列推导同日期日收益对(组合日收益 = 相邻 agent_nav 之比减一;基准日收益 = 相邻 benchmark_nav 之比减一;仅取两序列均非空的日期,首个盯市日不计入),β 为 OLS 斜率 `Σ((rb−μb)(ra−μa))/Σ((rb−μb)²)`;α 为日频 CAPM 残差年化 `(μa − rf/252 − β×(μb − rf/252))×252`,rf 与夏普同源(`TRACK_RISK_FREE_RATE`,默认 0.02)。重叠日收益对 < 20 时 β 与 α SHALL 为 null(不产出噪声读数)。`agent_metrics_daily` 新增 `beta`/`jensen_alpha` 列 SHALL 经幂等迁移写入(PRAGMA 探测,旧库自动补列),历史快照可经手动重算补齐。
(Previously: 仅要求样本量/胜率/平均超额/年化收益/波动率/夏普/最大回撤/风险分八项,无 β/α。)

#### Scenario: 指标快照

- **WHEN** `metrics-snapshot` 任务运行
- **THEN** agent_metrics_daily 写入当日全量指标行,重跑幂等(同日覆盖)

#### Scenario: β/α 正常计算

- **GIVEN** equity 双净值序列有 ≥ 20 个重叠日收益对,组合日收益与基准日收益存在稳定线性关系(β=0.8)
- **WHEN** 指标引擎重算
- **THEN** beta ≈ 0.8(OLS 斜率),jensen_alpha 按 CAPM 残差年化,两值随快照落库

#### Scenario: 样本不足时置空

- **GIVEN** 重叠日收益对 < 20(如当前净值曲线仅 17 个交易日)
- **WHEN** 指标引擎重算
- **THEN** beta 与 jensen_alpha 为 null,其余指标不受影响
- **AND** 快照落库 null 值,overview 不展示误导性读数

#### Scenario: 旧库幂等迁移

- **GIVEN** 已有 agent_metrics_daily 表但无 beta/jensen_alpha 列的存量库
- **WHEN** 初始化建表逻辑运行
- **THEN** 两列经 ALTER TABLE 补齐,既有数据不丢,重跑不重复加列
