# Tasks: update-price-chart-kline

- [ ] 后端数据采集：`collect_chart_data` 输出 OHLCV/MA5·20·60/决策价位，决策价位缺失形态（neutral·hold·未审批·历史 state·半缺）逐形态降级不报错，kline 缺失沿用跳过语义（单测全绿）
- [ ] 后端 OHLC 不变式守卫：按中文列名取数 + `high≥max(open,close)`、`low≤min(open,close)` 断言进测试
- [ ] 服务端 PNG：`_chart_stock_price` 重绘为蜡烛主图+成交量副图+均线叠加+决策价位水平线+财报日标注保留，图表 key/文件名不变（单测验证产物生成）
- [ ] 前端 K 线：`StockPriceChart` 改造为 ECharts candlestick + 成交量副图 + MA 叠加 + markLine 决策价位 + dataZoom/tooltip（组件测试两分支全绿）
- [ ] 历史会话后向兼容：close-only chartData 降级为收盘折线渲染，不报错不空白（组件测试覆盖）
- [ ] E2E spec 覆盖核心场景（股价图 K 线渲染 + 历史会话降级），e2e 门禁全绿
- [ ] 真实会话人工验证（PNG 与前端观感：250 根密度/涨跌配色/参考线可读性），报告落 `tests/validation/`
