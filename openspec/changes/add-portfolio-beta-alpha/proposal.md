# Proposal: add-portfolio-beta-alpha

## Why

战绩页能回答"组合赚了多少"(净值/年化/夏普/回撤),也能回答"跑赢了哪些指数"(PR #203 对比卡片),但回答不了"收益里多少来自跟着大盘走、多少来自独立判断"——即组合 β(市场敞口)与 Jensen α(剔除大盘后的残差)。用户已经需要这个拆解来正确解读"跑赢指数"(跌市高回避结构下,跑赢主要来自低 β,不能读成选股能力),目前只能靠人工计算。

## What Changes

- **指标引擎扩展**:`compute_metrics_from_marks` 基于同日期双日收益序列(组合 agent 净值日收益 vs 沪深300 基准日收益)OLS 回归计算**组合 β**;按 CAPM 计算年化 **Jensen α**(无风险利率沿用 `TRACK_RISK_FREE_RATE`,默认 2%);重叠样本 < 20 个交易日时两字段为 null(不展示误导性读数)
- **快照与 API 落库**:`agent_metrics_daily` 表幂等加列 `beta` / `jensen_alpha`(沿既有 ALTER TABLE 迁移模式);指标快照日批写入;`GET /api/v1/track-record/overview` 的 portfolio 块新增两字段
- **战绩页总览两格**:指标区新增「β(市场敞口)」与「α(年化超额)」两个指标位,沿既有指标卡样式,null 时显示 "—"

## Capabilities

### New Capabilities
(无)

### Modified Capabilities
- `track-record-metrics`: 风险收益指标引擎新增 β/α 输出(计算口径、样本门槛、快照列);净值曲线行为不变
- `frontend`: 战绩页总览指标区新增 β/α 两个指标位

## Impact

- 后端:`src/finance_agent/outcome/track_record/metrics.py`(计算)、`model.py`(迁移+快照读写)、`api.py`(overview 输出)
- 前端:`frontend/src/pages/trackRecord/TrackRecordPage.tsx`(两格)、`types.ts`
- 数据:agent_metrics_daily 加两列(幂等迁移,旧库自动补列);历史快照可手动重算补齐
- 不影响:equity_curve 口径、判定链路、PR #203 的 index-compare(相互独立,可并行合入)
