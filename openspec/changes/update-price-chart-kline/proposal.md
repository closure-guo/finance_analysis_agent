# Proposal: update-price-chart-kline

## Why

报告的「交易决策」章给出入场价/止损价/目标价，技术面引用 MA60、ATR、近 60 日高低，但报告中唯一的价格图（「股价趋势」）只有收盘价折线——读者无法在图上核验这些价位落在近期波动结构的什么位置，成交量维度则完全缺失。而完整 OHLCV（250 日前复权，三级回退）早已在 `state["kline"]` 中，`collect_chart_data` 只取了收盘一列；把收盘折线升级为 K 线图不引入任何新数据依赖，却让决策价位第一次变得可视化可核验。

## What Changes

- **股价图升级为 K 线图**：现有「股价趋势」图（`chart_stock_price`）由收盘折线+面积改为——蜡烛主图 + MA5/MA20/MA60 均线叠加 + 成交量副图 + 交易决策价位（入场/止损/目标，在场时）水平参考线；保留财报发布日标注（现状能力不回退）
- **chart_data.price 扩展**（additive）：每交易日条目增加开/高/低/成交量字段；新增 MA5/MA20/MA60 序列（口径与 derived 技术指标一致）；新增决策价位字段（缺失不携带）
- **双端同数据渲染**：服务端 matplotlib 重绘 `chart_stock_price` PNG（文件名/图表 key 不变，导出链路零改动）；前端 `StockPriceChart` 改为 ECharts candlestick（dataZoom/tooltip 交互）
- **历史会话后向兼容**：升级前会话的 chart_data 无 OHLC 字段时，前端股价图降级为收盘价折线渲染，不报错不空白
- **窗口与复权口径不变**：最近 250 个交易日、前复权，与现有风险指标窗口一致；不触碰行情拉取链路（`fetch_kline` 三级回退沿用 data-source-resilience 既有条款）

## Capabilities

### New Capabilities

- `report-kline-chart`: 报告股价 K 线图能力——K 线图表数据采集契约（OHLCV/均线/决策价位/降级）、服务端 PNG 与前端 ECharts 双端渲染、涨跌配色、历史会话后向兼容

### Modified Capabilities

（无——`frontend` 的 ChartsSection 渲染、主题配色、暗色可读条款均为图表无关的通用条款，继续适用；`report-export` 的图片嵌入条款为通用 PNG 嵌入，文件名不变故不涉改）

## Impact

- 后端：`src/finance_agent/charts.py`（`collect_chart_data` 扩展 + `_chart_stock_price` 重绘蜡烛图，不引新依赖）
- 前端：`frontend/src/Charts.tsx`（StockPriceChart 改造）及 chartData 类型定义（新增 optional 字段）
- 数据：零变更——消费既有 `state["kline"]` 与 `state["final_trade_decision"]`/`trader_plan`
- 不影响：`akshare_client.py` 行情拉取、export 导出器族（PNG 走既有嵌入链路）、其余 12 张图表、openspec 其他 spec
- 测试：后端 charts 单测扩展（数据采集契约 + PNG 生成）、前端组件测试（K 线/降级分支）、E2E spec（图表渲染场景，交互类变更走完整管线）
