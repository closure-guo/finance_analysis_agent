# Design: update-price-chart-kline

## Approach

**数据层**（`src/finance_agent/charts.py` `collect_chart_data`）：`price.daily` 条目在 `date`/`close` 基础上增加 `open`/`high`/`low`/`volume`（additive，历史消费者不受影响）；新增 `price.ma = {ma5, ma20, ma60}` 三条序列，从 close 序列按窗口计算简单移动平均，窗口前段为 `null` 逐日对齐；新增 `price.decision_levels`，取 `state["final_trade_decision"] or state["trader_plan"]` 的 `entry_price`/`stop_loss`/`target_price`（属性/字典双读取，与 `report.py` `_format_trade_decision` 同源逻辑），缺失的价位字段不进 dict。52 周高低推算逻辑不动。

**服务端 PNG**（`_chart_stock_price` 重写）：matplotlib 手绘蜡烛（影线 `vlines` + 实体 `bar`，不引入 mplfinance），双子图布局（gridspec 主图:成交量 ≈ 3:1），主图叠加 MA5/20/60 三线与决策价位水平虚线（右端文字标签「入场/止损/目标」），保留财报发布日竖线标注。**图表 key 与 PNG 文件名保持 `chart_stock_price` 不变**——导出器、文件清单、前端组件映射零改动，report-export 的 base64 嵌入自动生效。

**前端**（`frontend/src/Charts.tsx` `StockPriceChart`）：ECharts `candlestick` 系列（数据序 `[open, close, low, high]`）+ 副图成交量 bar（`xAxisIndex` 联动）+ 三条 MA line 系列 + 决策价位 `markLine`（带区分 label）+ tooltip formatter（开高低收/涨跌幅/成交量/均线值）；dataZoom 由单图改为双 xAxis 联动。类型定义中 `price.daily` 新字段全部 optional，新增 `price.ma?`/`price.decision_levels?`。组件内渲染分支：首日条目无 `open` 字段（历史会话）→ 走现有收盘折线实现，实现降级要求。

## Alternatives Considered

- **新增第 14 张图、保留收盘折线**：拒绝——同一标的的价格信息分散两图冗余，报告本已很长；原位升级保持 13 张图与章节结构不变。
- **引入 mplfinance 画蜡烛**：拒绝——新增依赖，且绕过现有 `_style_ax` 统一风格与中文字体处理；手绘蜡烛约 20 行成本。
- **只改前端 ECharts、PNG 保留折线**：拒绝——导出报告（md/pdf，用户转发阅读的主要形态）与前端不一致；决策价位参考线恰恰在导出件里最有用。
- **决策价位用 markPoint（单日点标注）而非水平线**：拒绝——水平线可跨全窗口对照历史价位结构，点标注只能标记右端一日。

## Risks

- **250 根蜡烛在 PNG 中过密**：figsize 适当加宽加高、蜡烛线宽按样本数自适应；若实测仍不可读，PNG 侧备选聚合为周线（均线/决策价位语义不变）——默认不动窗口（与风险指标窗口一致），实测后再定。
- **前复权序列上画实时决策价位**：qfq 右端点即现价，参考线与近端可比；窗口内除权除息会使历史段相对价位线轻微错位——与行情软件一致的既有口径，接受，不在本变更处理。
- **决策价位缺失形态多**（neutral/hold 无价位、审批未通过、历史 state、字段半缺）：统一「缺哪条不画哪条」降级，单测逐形态覆盖，不抛错。
- **图表列位错位（incident #240 教训）**：全程按 `akshare_client` 归一化后的中文列名（开盘/最高/最低/收盘/成交量）取数，禁止列位索引；单测断言 `high ≥ max(open, close)`、`low ≤ min(open, close)` 不变式，抓上游数据形态异常。
- **chart_data 体积增长**：daily 条目 2→6 字段 + 三条均线序列（250 日），session store 增量数十 KB 量级，可接受。

## Testing

- 后端 pytest：`collect_chart_data` 契约（OHLCV 输出/MA 对齐/决策价位各形态/缺失降级）+ `_chart_stock_price` PNG 生成 + OHLC 不变式断言。
- 前端 vitest：StockPriceChart 两分支（OHLC 在场 → candlestick option；仅 close → 折线 option）+ markLine 生成。
- E2E（交互类变更，走 e2e-skills 工具链）：报告图表渲染场景扩展——分析完成后股价图以 K 线渲染；历史会话 close-only 降级渲染。selector 经真实浏览器探索获取。
- 人工验证：真实会话抽查 PNG 与前端观感（250 根密度/涨跌配色/参考线可读性），报告落 `tests/validation/`。
