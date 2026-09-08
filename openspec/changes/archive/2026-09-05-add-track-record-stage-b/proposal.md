# Proposal: add-track-record-stage-b

## Why

历史战绩阶段 A（add-track-record）已落地观点全量记录与基础统计，但设计档案 v1.0 的核心价值主张「收益与风险成对展示」（P4）尚未实现：无净值曲线、无回撤/波动/夏普/风险分，胜率之外没有任何风险维度——用户看到 61% 胜率也无法评估策略质量。

## What Changes

- 新增 `daily_marks` 表：每个交易日对全部 open 观点盯市（mark_price/cum_return/cum_excess）
- 新增 `equity_curve` 表：agent 组合净值（等权 1/N 日再平衡，空仓记 0）与基准净值
- 新增 `agent_metrics_daily` 表：日批重算样本量/胜率/平均超额/年化/回撤/波动/夏普/风险分（含切片 JSON 预留）
- 指标引擎：净值 → 年化收益/波动率/夏普（无风险利率默认 2%）/最大回撤/风险分 `clip(round(0.6*dd+0.4*vol),1,10)`（映射表配置化）
- 新增后台任务 `metrics-snapshot` + `daily-marking`（挂现有 APScheduler）
- 总览 API 扩展返回组合指标；战绩页总览区扩展风险卡 + 净值曲线图（ECharts）

## Capabilities

### New Capabilities

- `track-record-metrics`: 盯市/净值/组合指标计算引擎与展示（P4 收益与风险成对）

### Modified Capabilities

（无——track-record 既有需求不变，纯增量）

## Impact

- 数据：三张新表（同库 SQLite）；判定引擎不变
- 后端：`track_record/` 新增 metrics 模块；api 总览端点扩展
- 前端：战绩页净值曲线（ECharts）+ 风险指标卡
- 前置：阶段 A 已完成；依赖判定日批产出 resolved 数据
