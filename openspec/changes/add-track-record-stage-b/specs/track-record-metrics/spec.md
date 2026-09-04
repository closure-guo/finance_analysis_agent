# track-record-metrics Specification Delta

## ADDED Requirements

### Requirement: 每日盯市记录

系统 SHALL 每个交易日对全部 status=open 观点写入 `daily_marks` 记录（mark_date/mark_price/cum_return/cum_excess），停牌或缺数据时跳过且不报错。

#### Scenario: 正常盯市

- **WHEN** 日批 `daily-marking` 任务运行且 open 观点对应标的有当日收盘价
- **THEN** 写入一条 daily_marks，cum_return 与 cum_excess 相对 entry_price 与基准同步期收益计算

#### Scenario: 缺数据容错

- **WHEN** 标的当日无行情（停牌/接口失败）
- **THEN** 该观点当日不产生 daily_marks，任务继续处理其余观点且整体返回成功

### Requirement: 组合净值曲线

系统 SHALL 基于 open+resolved 观点维护 `equity_curve`：等权 1/N 日再平衡、空仓日记 0 收益，同步记录基准净值供叠加对比。

#### Scenario: 净值计算

- **WHEN** 日批任务运行
- **THEN** equity_curve 追加当日 agent 净值与基准净值，空仓日 agent 日收益为 0

### Requirement: 风险收益指标引擎

系统 SHALL 日批重算 `agent_metrics_daily`：样本量/胜率/平均超额/年化收益/波动率/夏普（无风险利率默认 2%，配置化）/最大回撤/风险分 `clip(round(0.6*dd+0.4*vol),1,10)`（映射表配置化）。

#### Scenario: 指标快照

- **WHEN** `metrics-snapshot` 任务运行
- **THEN** agent_metrics_daily 写入当日全量指标行，重跑幂等（同日覆盖）

### Requirement: 总览展示风险维度

总览 API SHALL 返回组合指标（年化/回撤/夏普/风险分），战绩页 SHALL 展示净值曲线图与风险卡，收益与风险成对出现（P4）。

#### Scenario: 页面成对展示

- **WHEN** 用户打开历史战绩页
- **THEN** 总览区同时呈现收益类（胜率/平均超额/年化）与风险类（回撤/波动/夏普/风险分）指标及净值曲线
