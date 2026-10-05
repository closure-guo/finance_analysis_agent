# Proposal: add-index-performance-compare

## Why

历史战绩页目前只能把组合净值与沪深 300 单条基准线叠加对比,无法回答用户最直觉的问题:「这段时间到底跑赢了哪些指数?」。主流股票/基金交易软件普遍提供「跑赢指数对比」视图(组合区间收益 vs 一组主要指数同期收益的横向对比),这是评估交易能力的最直观入口。同时基础设施侧只落库了 000300 一条指数序列,扩展任何多指数对比都无数据可用。

## What Changes

- **指数收盘价存储**:新增 `index_closes` 表(index_code, trade_date, close),日批(盯市任务)每日拉取一组主要指数收盘并幂等落库,支持按历史区间回填;单指数拉取失败仅跳过该指数,不影响盯市主链路
- **指数对比读数 API**:新增 `GET /api/v1/track-record/index-compare` 端点——输入时间跨度(all/3m/6m/1y),返回组合区间累计收益 + 各指数同期区间收益 + 跑赢/跑输标记;组合收益口径 = equity_curve 净值首尾比,指数收益 = index_closes 同窗口首尾比
- **战绩页「跑赢指数对比」视图**:在 track-record 页新增对比卡片——选定跨度内组合收益横条 + 各指数收益横条(跑赢绿色↑/跑输红色↓),标题给出「跑赢 N/M 个指数」摘要
- **判定口径不动**:win/loss 判定基准仍为沪深 300 单基准(`docs/evals/metrics.md` 预登记口径),本变更纯属展示层对比,不触碰 settle/judgment 链路

## Capabilities

### New Capabilities
- `index-comparison`: 指数收益对比读数能力——多指数收盘存储、区间收益计算、跑赢/跑输对比 API 及战绩页对比视图

### Modified Capabilities
- `track-record-metrics`: 盯市日批新增多指数收盘落库职责(index_closes 表,单指数失败隔离);equity-curve 输出保持不变
- `frontend`: 战绩页新增「跑赢指数对比」视图卡片,时间跨度沿用 fa_track_prefs.timeSpan

## Impact

- 后端:`src/finance_agent/outcome/track_record/`(model.py 建表、marking.py 日批扩展、metrics.py 或新模块区间收益计算)、`src/finance_agent/api.py`(新端点)
- 前端:`frontend/src/pages/trackRecord/TrackRecordPage.tsx`(新卡片)、`frontend/src/types`(响应类型)
- 数据:sessions.db 新表 index_closes;首启需历史回填(拉取近 1 年)
- 数据源:AKShare `fetch_index_kline`(东财→新浪回退已有),新增每日 5-7 次指数调用,失败隔离语义沿 data-source-resilience
- 不影响:判定/结算链路、equity_curve 表结构、settings-center 偏好结构(复用 timeSpan,不改)
